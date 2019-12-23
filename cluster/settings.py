import ast
import atexit
import json
import os
import pickle
import sys
import time
import traceback
from datetime import datetime
from warnings import warn

import pyuv

import cluster.submission_state as submission_state
from cluster.utils import recursive_objectify, recursive_dynamic_json, load_json, update_recursive
from .communication_server import MessageTypes
from .constants import *
from .optimizers import Metaoptimizer, NGOptimizer, GridSearchOptimizer
from .utils import flatten_nested_string_dict, save_dict_as_one_line_csv, create_dir


def save_settings_to_json(setting_dict, model_dir):
  filename = os.path.join(model_dir, JSON_SETTINGS_FILE)
  with open(filename, 'w') as file:
    file.write(json.dumps(setting_dict, sort_keys=True, indent=4))


def send_results_to_server(metrics):
  print('Sending results to: ',
        (submission_state.communication_server_ip, submission_state.communication_server_port))
  loop = pyuv.Loop.default_loop()
  udp = pyuv.UDP(loop)
  udp.try_send((submission_state.communication_server_ip, submission_state.communication_server_port),
               pickle.dumps((MessageTypes.JOB_SENT_RESULTS, (submission_state.job_id, metrics))))


def exit_for_resume(only_on_cluster_submissions=True):
  if only_on_cluster_submissions and not submission_state.connection_active:
    return
  atexit.unregister(report_exit_at_server)  # Disable exit reporting
  sys.exit(3)  # With exit code 3 for resume


def save_metrics_params(metrics, params, save_dir=None):
  if save_dir is None:
    save_dir = params.model_dir
  create_dir(save_dir)
  save_settings_to_json(params, save_dir)

  param_file = os.path.join(save_dir, CLUSTER_PARAM_FILE)
  flattened_params = dict(flatten_nested_string_dict(params))
  save_dict_as_one_line_csv(flattened_params, param_file)

  time_elapsed = time.time() - update_params_from_cmdline.start_time
  if 'time_elapsed' not in metrics.keys():
    metrics['time_elapsed'] = time_elapsed
  else:
    warn('\'time_elapsed\' metric already taken. Automatic time saving failed.')
  metric_file = os.path.join(save_dir, CLUSTER_METRIC_FILE)

  for key, value in metrics.items():
    if str(type(value)) == "<class 'torch.Tensor'>":  # Hacky check for torch tensors without importing torch
      metrics[key] = value.item()  # silently convert to float

  save_dict_as_one_line_csv(metrics, metric_file)
  if submission_state.connection_active:
    send_results_to_server(metrics)


def is_json_file(cmd_line):
  try:
    return os.path.isfile(cmd_line)
  except Exception as e:
    warn('JSON parsing suppressed exception: ', e)
    return False


def is_parseable_dict(cmd_line):
  try:
    res = ast.literal_eval(cmd_line)
    return isinstance(res, dict)
  except Exception as e:
    warn('Dict literal eval suppressed exception: ', e)
    return False


def register_at_server(final_params):
  print('Sending registration to: ',
        (submission_state.communication_server_ip, submission_state.communication_server_port))
  loop = pyuv.Loop.default_loop()
  udp = pyuv.UDP(loop)
  udp.try_send((submission_state.communication_server_ip, submission_state.communication_server_port),
               pickle.dumps((MessageTypes.JOB_STARTED, (submission_state.job_id,))))


def report_error_at_server(exctype, value, tb):
  print('Sending errors to: ',
        (submission_state.communication_server_ip, submission_state.communication_server_port))
  loop = pyuv.Loop.default_loop()
  udp = pyuv.UDP(loop)
  traceback.print_exception(exctype, value, tb)
  udp.try_send((submission_state.communication_server_ip, submission_state.communication_server_port),
               pickle.dumps((MessageTypes.ERROR_ENCOUNTERED, (submission_state.job_id, traceback.format_exception(exctype, value, tb)))))


def report_exit_at_server():
  print('Sending confirmation of exit to: ',
        (submission_state.communication_server_ip, submission_state.communication_server_port))
  loop = pyuv.Loop.default_loop()
  udp = pyuv.UDP(loop)
  udp.try_send((submission_state.communication_server_ip, submission_state.communication_server_port),
               pickle.dumps((MessageTypes.JOB_CONCLUDED, (submission_state.job_id,))))


def update_params_from_cmdline(cmd_line=None, default_params=None, custom_parser=None, make_immutable=True,
                               verbose=True, dynamic_json=True):
  """ Updates default settings based on command line input.

  :param cmd_line: Expecting (same format as) sys.argv
  :param default_params: Dictionary of default params
  :param custom_parser: callable that returns a dict of params on success
  and None on failure (suppress exceptions!)
  :param register_job: Boolean whether to register the job to the communication server
  :param verbose: Boolean to determine if final settings are pretty printed
  :return: Immutable nested dict with (deep) dot access. Priority: default_params < default_json < cmd_line
  """

  if not cmd_line:
    cmd_line = sys.argv

  if default_params is None:
    default_params = {}

  try:
    connection_details = ast.literal_eval(cmd_line[1])
    submission_state.communication_server_ip = connection_details['ip']
    submission_state.communication_server_port = connection_details['port']
    submission_state.job_id = connection_details['id']
    del cmd_line[1]
    submission_state.connection_active = True
  except:
    print("Could not parse connection info, presuming the job to be run locally")    

  if len(cmd_line) < 2:
    cmd_params = {}
  elif custom_parser and custom_parser(cmd_line):  # Custom parsing, typically for flags
    cmd_params = custom_parser(cmd_line)
  elif len(cmd_line) == 2 and is_json_file(cmd_line[1]):
    cmd_params = load_json(cmd_line[1])
  elif len(cmd_line) == 2 and is_parseable_dict(cmd_line[1]):
    cmd_params = ast.literal_eval(cmd_line[1])
  else:
    raise ValueError('Failed to parse command line')

  update_recursive(default_params, cmd_params)

  if JSON_FILE_KEY in default_params:
    json_params = load_json(default_params[JSON_FILE_KEY])
    if 'default_json' in json_params:
      json_base = load_json(json_params[JSON_FILE_KEY])
    else:
      json_base = {}
    update_recursive(json_base, json_params)
    update_recursive(default_params, json_base)

  update_recursive(default_params, cmd_params)

  if "__timestamp__" in default_params:
    raise ValueError("Parameter name __timestamp__ is reserved!")

  if dynamic_json:
    objectified = recursive_objectify(default_params, make_immutable=make_immutable)
    timestamp = datetime.now().strftime('%H:%M:%S-%d%h%y')
    namespace = dict(__timestamp__=timestamp, **objectified)
    recursive_dynamic_json(default_params, namespace)
  final_params = recursive_objectify(default_params, make_immutable=make_immutable)

  if verbose:
    print(json.dumps(final_params, indent=4, sort_keys=True))

  if submission_state.connection_active:
    register_at_server(final_params.get_pickleable())
    sys.excepthook = report_error_at_server
    atexit.register(report_exit_at_server)
  update_params_from_cmdline.start_time = time.time()
  return final_params


update_params_from_cmdline.start_time = None

optimizer_dict = {'cem_metaoptimizer': Metaoptimizer,
                  'nevergrad': NGOptimizer,
                  'gridsearch': GridSearchOptimizer}
