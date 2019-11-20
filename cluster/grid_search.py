import os
import shutil
import sys
import git
from pathlib2 import Path

from cluster import cluster_run, execute_submission, update_params_from_cmdline
from cluster.report import produce_basic_report, init_plotting
from cluster.utils import mkdtemp, get_git_url


if __name__ == '__main__':

    init_plotting()


    params = update_params_from_cmdline(verbose=False)

    json_full_name = os.path.abspath(sys.argv[1])
    home = str(Path.home())

    main_path = mkdtemp(suffix=f"{params.optimization_procedure_name}-project")
    results_path = os.path.join(home, params.results_dir, params.optimization_procedure_name)
    jobs_path = mkdtemp(suffix=f"{params.optimization_procedure_name}-jobs")


    given_url = params.git_params.get("url")
    if not given_url:
        auto_url = get_git_url()
        if not auto_url:
            raise git.exc.InvalidGitRepositoryError("No git repository given in json file or auto-detected")

        git_params = dict(url=auto_url, local_path=main_path, **params.git_params)

    else:
        git_params = dict(local_path=main_path, **params.git_params)


    base_paths_and_files = dict(
        script_to_run=os.path.join(main_path, params.script_relative_path),
        result_dir=results_path,
        jobs_dir=jobs_path,
        **params.environment_setup
    )

    hyperparam_dict = {hyperparam["param"]: hyperparam["values"] for hyperparam in params.hyperparam_list}

    all_args = dict(
        submission_name=params.optimization_procedure_name,
        paths=base_paths_and_files,
        submission_requirements=params.cluster_requirements,
        hyperparam_dict=hyperparam_dict,
        other_params=params.fixed_params,
        samples=params.get('samples', None),
        restarts_per_setting=params.restarts,
        smart_naming=params.get('smart_naming', True),
        git_params=git_params,
    )

    submission = cluster_run(**all_args)

    df, all_params, metrics, submission_hook_stats = execute_submission(submission, base_paths_and_files["result_dir"])
    df.to_csv(os.path.join(base_paths_and_files["result_dir"], "results_raw.csv"))

    relevant_params = list(hyperparam_dict.keys())
    output_pdf = os.path.join(base_paths_and_files["result_dir"], f"{params.optimization_procedure_name}_report.pdf")
    produce_basic_report(
        df,
        relevant_params,
        metrics,
        submission_hook_stats=submission_hook_stats,
        procedure_name=params.optimization_procedure_name,
        output_file=output_pdf,
    )

    # copy this script to the result dir
    my_path = os.path.realpath(__file__)
    shutil.copy(my_path, base_paths_and_files["result_dir"])
