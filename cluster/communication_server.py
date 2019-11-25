import socket
import pyuv
import signal
import pickle
import collections
import threading
import time

msg_types = {0: 'job_started',
             1: 'error_encountered',
             2: 'job_concluded'}

class Job():
  def __init__(self, id, settings, status):
    self.id =  id
    self.settings = settings
    self.status = status

class CommunicationServer():

  def __init__(self):
    self.ip_adress = self.get_own_ip()
    self.port = None
    print("Running on IP: ", self.ip_adress)
    self.start_listening()

    self.jobs = []

  @property
  def connection_info(self):
    if self.ip_adress is None or self.port is None:
      raise ValueError('Either IP adress or port are not known yet.')
    return self.ip_adress, self.port

  def get_own_ip(self):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
      # doesn't even have to be reachable
      s.connect(('10.255.255.255', 1))
      IP = s.getsockname()[0]
    except:
      IP = '127.0.0.1'
    finally:
      s.close()
    return IP

  def start_listening(self):
    def on_read(handle, ip_port, flags, data, error):
      if data is not None:
        #handle.send(ip_port, data) This would be a way to ensure messaging worked well
        msg_type_idx, message = pickle.loads(data)
        if msg_types[msg_type_idx] == 'job_started':
          self.handle_job_started(message)
        elif msg_types[msg_type_idx] == 'error_encountered':
          self.handle_error_encountered(message)
        elif msg_types[msg_type_idx] == 'job_concluded':
          self.handle_job_concluded(message)
        else:
          self.handle_unidentified_message(data, msg_type_idx, message)

    def async_exit(async):
      async.close()
      signal_h.close()
      server.close()

    def signal_cb(sig, frame):
      async.send(async_exit)

    loop = pyuv.Loop.default_loop()
    async = pyuv.Async(loop)

    server = pyuv.UDP(loop)
    server.bind((self.ip_adress, 0))
    self.port = server.getsockname()[1]
    print("Running on Port: ", self.port)
    server.start_recv(on_read)

    signal_h = pyuv.Signal(loop)
    signal_h.start(signal_cb, signal.SIGINT)

    t = threading.Thread(target=loop.run, daemon=True)
    t.start()

    signal.signal(signal.SIGINT, signal_cb)


  def handle_job_started(self, message):
    job_id, settings = message
    print("Job Started ", job_id, ' at time ', time.time())
    if not self.get_job(job_id) is None:
      raise ValueError('Job was already in the list of jobs but claims to just have been started.')
    self.jobs.append(Job(job_id, settings, 0))


  def handle_error_encountered(self, message):
    job_id, settings = message
    job = self.get_job(job_id)
    if job is None:
      raise ValueError('Job was not in the list of jobs but encountered an error... fucked up twice, huh?')
    job.status = 1


  def handle_job_concluded(self, message):
    job_id, metrics, settings = message
    job = self.get_job(job_id)
    print("Job Concluded ", job_id, ' at time ', time.time())
    if job is None:
      raise ValueError('Job was not in the list of jobs but claims to just have concluded.')
    job.status = 2


  def handle_unidentified_message(self, data, msg_type_idx, message):
    print("Received a message I did not understand:")
    print(data)
    print(msg_type_idx, type(msg_type_idx))
    print(msg_types[msg_type_idx], type(msg_types[msg_type_idx]))
    print(message, type(message))

  def get_job(self, id):
    for job in self.jobs:
      if job.id == id:
        return job
    return None

  @property
  def running_jobs(self):
    return [job for job in self.jobs if job.status == 0]

  @property
  def n_running_jobs(self):
      return len(self.running_jobs)

  @property
  def concluded_jobs(self):
    return [job for job in self.jobs if job.status == 2]

  @property
  def n_concluded_jobs(self):
    return len(self.concluded_jobs)

  @property
  def failed_jobs(self):
    return [job for job in self.jobs if job.status == 1]

  @property
  def n_failed_jobs(self):
    return len(self.failed_jobs)


  def __repr__(self):
    return ('Communication Server Information \n'
            'Running: {.n_running_jobs}, Failed: {.n_failed_jobs}, Completed: {.n_concluded_jobs}').format(*(3 * [self]))