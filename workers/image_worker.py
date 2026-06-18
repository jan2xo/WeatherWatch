from helpers.image import compose_weather_card


def run_image_job(job):
    return compose_weather_card(
        input_path=job["raw_output_path"],
        output_path=job["final_output_path"],
        title=job["title"],
        subtitle=job["subtitle"],
        source=job["source"],
    )