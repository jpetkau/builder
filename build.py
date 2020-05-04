import subprocess
import memo
import os
import logging

logger = logging.getLogger(__name__)

"""
Easy error to make:

- step 1 runs a tool that generates `out.txt`
- instead of returning a Blob, it returns a Path
- steps 2/3/4 pass that Path along
- step 5 reads from that Path

This will work but nobody will be hashed correctly.
Step 5 should not be allowed to use the path without passing in the
maching dir it came from.

WAIT NO IS THAT REALLY A PROBLEM?
- yes if step 5 takes a gen path as input; gen paths *can't* be inputs.
- what actually happens?
  - we decide not to rerun step 1 because inputs haven't changed; just grab output path from memo.
  - step 5 tries to turn that into a blob and gets file not found.
  - problem is that step 5 shouldn't have the "real" fs as input; it should have the output fs from step 1.

- this should be fixable in Path itself:
    - step 1 got an *output* path, different from an input path
    - can't read from an output path without shenanigans
    - or it already encodes the proper dependency (we can do this since it's
      based on the memo anyway)

In general: going from a pure path that refers to a generated file, to
the actual file, shouldn't be possible. The generation step must return
an actual ref to the file, or a tree plus a path. Or the path-to-file
logic must notice what tree it's reading, and automatically include the
step that produced that tree as a dependency.

This is really common so we want to make it easy.

Ok so "fs.output_dir()" returns a special object:
- We can make writable subpaths into it
- Those subpaths look like "(gendir, rel)", i.e. their root is that particular output dir, not the top-level output dir.
- When the function with that output dir returns, that output dir object turns into a Tree object. (Or a partial tree?) - if one of those paths gets passed to another function, do we have to materialize the whole tree or just the passed-in part?
- in pure fn terms there's no problem here; the problem is just that it's so easy for a function that takes "foo.c" as input to assume "foo.h" is coming along for the ride.

"""


def argstr(arg):
    if type(arg) is str:
        return arg
    if hasattr(arg, "__fspath__"):
        return os.fspath(arg)
    raise TypeError(f"don't know how to use {arg} as a command line arg")


@memo.memoize
def run_tool(*args, stdin=os.devnull):
    logger.debug("Here I am in run tool")
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


if __name__ == '__main__':
    f1 = fs.Blob(b'hello')
