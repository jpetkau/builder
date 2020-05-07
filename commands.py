import subprocess, os, logging
import memo, fs, util, sys

logger = logging.getLogger(__name__)


@memo.memoize
def run_tool(*args, stdin=os.devnull):
    strargs = [os.fspath(arg) for arg in args]

    # make_output_dir should just construct a new random dir, not
    # a hash-based one, because our hash may be incomplete.
    odir = fs.make_output_dir()
    stdout = odir / "stdout"
    stderr = odir / "stderr"
    with open(stdin, "rb") as fin, open(stdout, "wb") as fout, open(
        stderr, "wb"
    ) as ferr:
        logger.info(f"run {strargs}")
        p = subprocess.run(
            strargs, stdin=fin, stdout=fout, stderr=ferr, cwd=odir, check=False
        )
    if p.returncode != 0:
        with open(stderr, "rb") as f:
            p.stderr = f.read()
            print(p.stderr, file=sys.stderr)
    return util.Struct(tree=odir.tree(), stdout=stdout.blob(), stderr=stderr.blob())


@memo.memoize
def cat(*files, fs):
    paths = fs.resolve_input_paths(files)
    return run_tool("/bin/cat", *paths).stdout


class InstalledTool:
    """Represents some preinstalled executable tool, like gcc.

  Assumes we can't tell what other crud it might depend on, so
  we have to trust whoever instanstiates this class.
  """

    def __init__(self, path, other_deps):
        self.__hash_value__ = hash(path, *other_deps)
        self.path = path

    def __vhash__(self):
        return

    @memo.memoize
    def __call__(self, args):
        ...


if __name__ == "__main__":
    f1 = fs.Blob(b"hello")
