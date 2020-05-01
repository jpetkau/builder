"""
Serve a store over http.

operations:

	GET blob/<hash>
	PUT blob/<hash>
    POST blob   -- hash is computed by server
    POST blob/<hash>   -- hash is validated by server

	GET tree/<hash>
	PUT tree/<hash>
	POST tree	-- hash is computed by server

	GET checktree/<hash> -- return a (partial) list of missing elements in the given tree
	GET checktree/<hash>?max=N
"""
__version__ = "0.1"


import BaseHTTPServer
import shutil


class ChaiRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    server_version = "ChaiHTTP/" + __version__

    def do_GET(self):
        f = self.send_head()
        if f:
            with f:
                shutil.copyfileobj(f, self.wfile)

    def do_HEAD(self):
        f = self.send_head()
        if f:
            f.close()

    """
    def do_POST(self):
        hash = self.parse_hash("put")
        f = self.server.store.open_temp_file()
        
        if self.server.store.contains_blob(hash):
            # It's quietly OK to re-send an existing blob
            self.send_response(200)
            shutil.copyfileobj(self.rfile, 
    """

    def send_head(self):
        """Send the common HTTP header for GET and HEAD requests. Returns
        a Blob object."""
        what, hash = self.parse_hash()
        if hash:
            blob = self.server.store.get_blob_reader(hash)
            if blob:
                self.send_response(200)
                self.send_header("Content-type", "application/octet-stream")
                self.end_headers()
                return blob
        self.send_error(404, "Object not found")
        return None

    def parse_hash(self):
        m = re.match("(blob|tree)/([0-9a-z]{40})$", self.path)
        if m:
            return m.group(1).decode("hex")
        else:
            return None


def run(store):
    server_address = ("", 8000)
    httpd = BaseHTTPServer.HTTPServer(server_address, ChaiRequestHandler)
    httpd.store = store
    httpd.serve_forever()


if __name__ == "__main__":
    "Serve out of a filesystem store in the current dir by default"
    import fs_store

    run()
