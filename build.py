import subprocess
import memo
import os

"""
Easy error to make:

- step 1 runs a tool that generates `out.txt`
- instead of returning a Blob, it returns a Path
- steps 2/3/4 pass that Path along
- step 5 reads from that Path

This will work but nobody will be hashed correctly.
Step 5 should not be allowed to use the path without passing in the
maching dir it came from.

- this should be fixable in Path itself:
    - step 1 got an *output* path, different from an input path
    - can't read from an output path without shenanigans
    - or it already encodes the proper dependency (we can do this since it's
      based on the memo anyway)

In general: going from a pure path that refers to a generated file, to
the actual file, sholdn't be possible. The generation step must return
an actual ref to the file, or a tree plus a path.

This is really common so we want to make it easy.
"""


def argstr(arg):
    if type(arg) is str:
        return arg
    if hasattr(arg, "__fspath__"):
        return os.fspath(arg)
    raise TypeError(f"don't know how to use {arg} as a command line arg")


@memo.memoize
def run_tool(*args, stdin=os.devnull):
    strargs = [argstr(arg) for arg in args]

    odir = fs.make_output_dir()
    stdout = odir / "stdout"
    stderr = odir / "stderr"
    with open(stdin, "rb") as fin, open(stdout, "wb") as fout, open(
        stderr, "wb"
    ) as ferr:
        p = subprocess.run(
            strargs, stdin=fin, stdout=fout, stderr=ferr, cwd=odir, check=True
        )
    return util.Struct(path=odir, stdout=stdout.blob(), stderr=stderr.blob())


@memo.memoize
def cat(*files, fs):
    paths = fs.resolve_input_paths(files)
    return run_tool("/bin/cat", *paths).stdout


class TargetOutputFile(NamedTuple):
    """
  Represents a single output file from another target
  Which do we hash on?
  - That target's inputs?
  - Or binary content hash?

  Definitely need to do the inputs. Content hash sometimes
  also helps, not always.
  """

    ...


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

    @memo
    def __call__(self, args):
        ...
