from helpers.browser import capture_page


def run_capture_job(job):
    return capture_page(
        url=job["url"],
        output_path=job["raw_output_path"],
    )