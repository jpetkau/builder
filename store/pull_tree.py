def store_from_url(src_url):
	
# Pull a tree from a remote server
if __name__ == '__main__':
	import sys
	src_url,dst_dir,hash = sys.argv[1:]
	src_store = store_from_url(src_url)
	sync.pull_tree(src_store, hash, fs.FS(dst_dir)
