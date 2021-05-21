import asyncio, aiohttp, os
import tqdm

r_semaphore = asyncio.Semaphore(10)


# get content and write it to file
def write_to_file(filename, content):
    f = open(filename, 'wb')
    f.write(content)
    f.close()


async def get(*args, **kwargs):
    response = await aiohttp.request('GET', *args, **kwargs)
    return response


async def head(*args, **kwargs):
    response = await aiohttp.request('HEAD', *args, **kwargs)
    return response


async def download_file(url, filepath, filename):
    async with r_semaphore:
        if os.path.isfile(filepath):
            # already downloaded
            pass
        else:
            async with aiohttp.request("GET", url, chunked=True) as media:
                media_length = int(media.headers.get("content-length"))
                if media.status == 200:
                    if os.path.isfile(filepath) and os.path.getsize(
                            filepath >= media_length):
                        # already downloaded
                        pass
                    else:
                        try:
                            with open(filepath, 'wb') as f:
                                async for chunk in media.content.iter_chunked(
                                        1024):
                                    if chunk:
                                        f.write(chunk)
                                f.close()
                                # success
                        except Exception as e:
                            raise e

                    if os.path.getsize(filepath) >= media_length:
                        pass
                    else:
                        print("Segment is corrupt")
                elif media.status == 404:
                    print("404")
                else:
                    print("Error fetching segment")


@asyncio.coroutine
def wait_with_progressbar(coros):
    for f in tqdm.tqdm(asyncio.as_completed(coros), total=len(coros)):
        yield from f