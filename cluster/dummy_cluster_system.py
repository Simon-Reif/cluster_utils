import logging
import os
from copy import copy
from .cluster_system import ClusterSubmission
from multiprocessing import cpu_count
import concurrent.futures
from subprocess import run, PIPE
from .constants import *
import random
import numpy as np

logger = logging.getLogger('cluster_utils')

class Dummy_ClusterSubmission(ClusterSubmission):
    def __init__(self, requirements, paths, remove_jobs_dir=True):
        super().__init__(paths, remove_jobs_dir)
        self._process_requirements(requirements)
        self.exceptions_seen = set({})
        self.available_cpus = range(cpu_count())
        self.futures_tuple = []
        self.executor = concurrent.futures.ProcessPoolExecutor(self.concurrent_jobs)

    def generate_cluster_id(self):
        cluster_id = np.random.randint(1e10)
        while cluster_id in [c_id for c_id, future in self.futures_tuple]:
            cluster_id = np.random.randint(1e10)
        return cluster_id

    def submit_fn(self, job):
        self.generate_job_spec_file(job)
        free_cpus = random.sample(self.available_cpus, self.cpus_per_job)
        free_cpus_str = ','.join(map(str, free_cpus))
        cmd = 'taskset --cpu-list {} bash {}'.format(free_cpus_str, job.run_script_path)
        cluster_id = self.generate_cluster_id()
        new_futures_tuple = (cluster_id, self.executor.submit(run, cmd, stdout=PIPE, stderr=PIPE, shell=True))
        logger.info(f"Job with id {job.id} submitted locally.")
        job.futures_object = new_futures_tuple[1]
        self.futures_tuple.append(new_futures_tuple)
        return cluster_id

    def stop_fn(self, job_id):
        for cluster_id, future in self.futures_tuple:
            if cluster_id == job_id:
                future.cancel()
        concurrent.futures.wait(self.futures)

    def generate_job_spec_file(self, job):
        job_file_name = '{}_{}.sh'.format(job.iteration, job.id)
        run_script_file_path = os.path.join(self.submission_dir, job_file_name)
        cmd = job.generate_execution_cmd(self.paths)
        # Prepare namespace for string formatting (class vars + locals)
        namespace = copy(vars(self))
        namespace.update(vars(job))
        namespace.update(locals())

        with open(run_script_file_path, 'w') as script_file:
            script_file.write(LOCAL_RUN_SCRIPT % namespace)
        os.chmod(run_script_file_path, 0O755)  # Make executable

        job.run_script_path = run_script_file_path

    def status(self, job):
        future = [future for cluster_id, future in self.futures_tuple if cluster_id == job.cluster_id]
        if len(future) == 0:
            return 0
        future = future[0]
        if future.running():
            return 2
        else:
            if future.done():
                if future.result().__dict__['returncode'] == 1:
                    return 4
                return 3
            return 1

    def is_blocked(self):
        return True

    @property
    def futures(self):
        return [future for _, future in self.futures_tuple]

    def _process_requirements(self, requirements):
        self.cpus_per_job = requirements['request_cpus']
        self.max_cpus = requirements.get('max_cpus', cpu_count())
        if self.max_cpus <= 0:
            raise ValueError('CPU limit must be positive. Not {}.'.format(self.max_cpus))
        self.available_cpus = min(self.max_cpus, cpu_count())
        self.concurrent_jobs = self.available_cpus // self.cpus_per_job
        if self.concurrent_jobs == 0:
            logger.warning('Total number of CPUs is smaller than requested CPUs per job. Resorting to 1 CPU per job')
            self.concurrent_jobs = self.available_cpus
        assert self.concurrent_jobs > 0

"""
    def check_error_msgs(self):
        failed = [future for _, future in self.futures_tuple if
                  future.done() and future.result().__dict__['returncode'] == 1]
        errs = set([future.result().stderr.decode() for future in failed])
        for err in errs:
            if err not in self.exceptions_seen:
                self.exceptions_seen.add(err)
                logger.warning(err)
        return len(errs) > 0
"""