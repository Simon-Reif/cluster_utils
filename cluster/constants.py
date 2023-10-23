CLUSTER_PARAM_FILE = "param_choice.csv"
CLUSTER_METRIC_FILE = "metrics.csv"
JSON_SETTINGS_FILE = "settings.json"
JOB_INFO_FILE = "job_info.csv"

METADATA_FILE = "metadata.json"
STATUS_PICKLE_FILE = "status.pickle"
FULL_DF_FILE = "all_data.csv"
REDUCED_DF_FILE = "reduced_data.csv"
REPORT_DATA_FILE = "report_data.pickle"
STD_ENDING = "__std"
RESTART_PARAM_NAME = "job_restarts"

OBJECT_SEPARATOR = "."

# note: must be hashable
PARAM_TYPES = (bool, str, int, float, tuple)

WORKING_DIR = "working_dir"
ID = "_id"
ITERATION = "_iteration"

RESERVED_PARAMS = (ID, ITERATION, RESTART_PARAM_NAME)

DISTR_BASE_COLORS = [
    (0.99, 0.7, 0.18),
    (0.7, 0.7, 0.9),
    (0.56, 0.692, 0.195),
    (0.923, 0.386, 0.209),
]

CONCLUDED_WITHOUT_RESULTS_GRACE_TIME_IN_SECS = 5.0
JOB_MANAGER_LOOP_SLEEP_TIME_IN_SECS = 0.2

MPI_CLUSTER_MAX_NUM_TOKENS = 10000

MPI_CLUSTER_RUN_SCRIPT = """
#!/bin/bash
# Submission ID %(id)d

%(cmd)s
rc=$?
if [[ $rc == 0 ]]; then
    rm -f %(run_script_file_path)s
    rm -f %(job_spec_file_path)s
elif [[ $rc == 3 ]]; then
    echo "exit with code 3 for resume"
    exit 3
elif [[ $rc == 1 ]]; then
    exit 1
fi
"""

MPI_CLUSTER_JOB_SPEC_FILE = """# Submission ID %(id)d
JobBatchName=%(opt_procedure_name)s
executable = %(run_script_file_path)s

error = %(run_script_file_path)s.err
output = %(run_script_file_path)s.out
log = %(run_script_file_path)s.log

request_cpus=%(cpus)s
request_gpus=%(gpus)s
request_memory=%(mem)s

%(requirements_line)s

on_exit_hold = (ExitCode =?= 3)
on_exit_hold_reason = "Checkpointed, will resume"
on_exit_hold_subcode = 2
periodic_release = ( (JobStatus =?= 5) && (HoldReasonCode =?= 3) && (HoldReasonSubCode =?= 2) )

# Inherit environment variables at submission time in job script
getenv=True

%(concurrent_line)s

%(extra_submission_lines)s

queue
"""


LOCAL_RUN_SCRIPT = """#!/bin/bash
# %(id)d

%(cmd)s
"""
