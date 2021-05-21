import os, threading, requests
from tqdm import tqdm


class FileDownloader():
    """
    @source: https://gist.github.com/stefanfortuin/9dbfe8618701507d0ef2b5515b165c5f
    """
    def __init__(self, max_threads=10):
        print("> Threaded downloader using {} threads.".format(
            str(max_threads)))
        self.sema = threading.Semaphore(value=max_threads)
        self.headers = {
            'user-agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36'
        }
        self.block_size = 1024

    def t_getfile(self, link, filepath, filename, bar, session):
        """ 
        Threaded function that uses a semaphore 
        to not instantiate too many threads 
        """

        self.sema.acquire()

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        if not os.path.isfile(filepath):
            headers = requests.head(link).headers
            if 'content-length' not in headers:
                print(f"server doesn't support content-length for {link}")
                self.sema.release()
                return

            total_bytes = int(requests.head(link).headers['content-length'])

            if not bar:
                bar = tqdm(total=total_bytes,
                           initial=0,
                           unit='B',
                           unit_scale=True,
                           desc=filename)
            self.download_new_file(link, filename, filepath, total_bytes, bar,
                                   session)
        else:
            current_bytes = os.stat(filepath).st_size

            headers = requests.head(link).headers
            if 'content-length' not in headers:
                print(f"server doesn't support content-length for {link}")
                self.sema.release()
                return

            total_bytes = int(requests.head(link).headers['content-length'])
            if not bar:
                bar = tqdm(total=total_bytes,
                           initial=current_bytes,
                           unit='B',
                           unit_scale=True,
                           desc=filename)
            if current_bytes < total_bytes:
                self.continue_file_download(link, filename, filepath,
                                            current_bytes, total_bytes, bar)
            else:
                # print(f"already done: {filename}")
                if bar.unit == "B":
                    bar.update(self.block_size)
                else:
                    bar.update(1)

        self.sema.release()

    def download_new_file(self, link, filename, filepath, total_bytes, bar,
                          session):
        if session == None:
            try:
                request = requests.get(link,
                                       headers=self.headers,
                                       timeout=30,
                                       stream=True)
                self.write_file(request, filepath, 'wb', bar)
            except requests.exceptions.RequestException as e:
                print(e)
        else:
            request = session.get(link, stream=True)
            self.write_file(request, filepath, 'wb', bar)

    def continue_file_download(self, link, filename, filepath, current_bytes,
                               total_bytes, bar):
        range_header = self.headers.copy()
        range_header['Range'] = f"bytes={current_bytes}-{total_bytes}"

        try:
            request = requests.get(link,
                                   headers=range_header,
                                   timeout=30,
                                   stream=True)
            self.write_file(request, filepath, 'ab', bar)
        except requests.exceptions.RequestException as e:
            print(e)

    def write_file(self, content, filepath, writemode, bar):
        with open(filepath, writemode) as f:
            for chunk in content.iter_content(chunk_size=self.block_size):
                if chunk:
                    f.write(chunk)
                    if bar.unit == "B":
                        bar.update(self.block_size)

        # print(f"completed file {filepath}", end='\n')
        f.close()
        bar.update(1)

    def get_file(self, link, path, filename, bar=None, session=None):
        """ Downloads the file"""
        thread = threading.Thread(target=self.t_getfile,
                                  args=(link, path, filename, bar, session))
        thread.start()
        return thread
