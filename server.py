import argparse
import asyncio
import logging
import os

import aiofiles
from aiohttp import web
from dotenv import load_dotenv


class Settings:
    def __init__(self, delay, photos_directory, logging_enable):
        self.delay = (
            int(delay) if delay is not None else int(os.getenv("RESPONSE_DELAY"))
        )
        self.photos_directory = (
            photos_directory
            if photos_directory is not None
            else os.getenv("BASE_PHOTOS_DIRECTORY")
        )
        self.logging_enable = logging_enable


def create_parser():
    parser = argparse.ArgumentParser(
        description="Create parser which allow us to use settings for load service"
    )
    return parser


async def uptime_handler(request):
    response = web.StreamResponse()

    response_delay = app["settings"].delay
    photos_directory = app["settings"].photos_directory
    logging_enable = app["settings"].logging_enable

    archive_name = request.match_info.get("archive_hash")
    if not os.path.exists(f"{photos_directory}/{archive_name}"):
        raise web.HTTPNotFound(text="Архив не существует или был удален")

    response.headers["Content-Disposition"] = f'attachment; filename="archive.zip'

    await response.prepare(request)

    args = ["zip", "-r", "-", "."]

    archive = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=f"{photos_directory}/{archive_name}",
    )
    try:
        while True:
            stdout = await archive.stdout.read(500 * 1024)
            if not stdout:
                break
            await asyncio.sleep(response_delay)
            if logging_enable:
                logging.info("Sending archive chunk ...")
            await response.write(stdout)
    except asyncio.CancelledError:
        if logging_enable:
            logging.debug("Download was interrupted")
        raise
    finally:
        archive.kill()
        await archive.communicate()
    return response


async def handle_index_page(request):
    async with aiofiles.open("index.html", mode="r") as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type="text/html")


if __name__ == "__main__":
    load_dotenv()

    parser = create_parser()
    parser.add_argument("-l", "--logging_enable", help="logging enable")
    parser.add_argument("-d", "--delay", help="response delay in seconds")
    parser.add_argument("-pdir", "--photos_directory", help="Path to photo directory")
    args = parser.parse_args()
    logging_enable = (
        args.logging_enable
        if args.logging_enable is not None
        else os.getenv("LOGGING_ENABLE", "False")
    ) == "True"
    app = web.Application()
    app["settings"] = Settings(args.delay, args.photos_directory, logging_enable)

    if logging_enable:
        logging.basicConfig(level=logging.DEBUG)

    app.add_routes(
        [
            web.get("/", handle_index_page),
            web.get("/archive/{archive_hash}/", uptime_handler),
        ]
    )
    web.run_app(app)
