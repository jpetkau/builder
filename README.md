builder
=======

This is an experiment in a build system with extensive memoization based
on pure function evaluation.

Python is used both for the underlying logic and for specifying build
configurations. This is for expediency while experimenting; since it's really
hard to keep things pure or immutable in Python, a real system should have
a different foundation.

It could still have a Python-like build syntax like Skylark though.

Plan so far
-----------

Memoization:
- Given a function `f` and args `args`, we store a map from `hash(f,args)` to `hash(f(args))`.

Yoneda stuff:
- For things like filesystem or options inputs: some functions return an additional argument, a list of sets of 'accesses' to the fs or options, along with results. The memoization logic trusts that this list is accurate, and will reuse a memoized result as long as inputs agree at these points. (Note that when this mechanism is used, the *first* entry in the list will be independent of the actual filesystem. Given the result of the first access, the *second* access is now independent, etc.)

Pseudo-nondeterminism:
- Everything is assumed to be pure and determinstic by default. For unavoidable but harmless nondeterminism (like a compiler that sticks a date in its output), functions or values can be marked to prevent spurious warnings.


Other details
-------------
- py functions are just normal functions
- build tree is exactly ordinary call tree. Lots of memoization.
- no magic laziness, but explicit laziness is ok
- no magic parallelism, but explicit parallelism ok

- All values are represented by content hashes
- Functions defined in the build are values too, hashable the same way
- "System" functions are hashed by name


Modules overview
----------------

In roughly bottom-to-top order:

`util.py`: misc. convenience utilities, not particular to this problem.

`cas.py`: content-addressable store and serialization

`context.py`: support for dynamically scoped options understood by memo system.

`memo.py`: function call memoization based on `cas`. Doesn't handle the incremental dependency tracking yet, but simple and easy to understand.

`fs.py`: `pure` model of file system. Useful objects:

    `Blob`: immutable byte string at some unspecified location.
    `Tree`: (fully hashed) immutable tree of blobs and trees at some unspecified location.
    `Path`: any path used during builds; need to use this instead of simple strings to get correct hashing.

    Blob and Tree can be materialized in a few different ways:
    - for read-only access where symlinks are ok, 
    - if a tool needs read/write access or can't deal with symlinks, copies can be made.

`y_memo.py`: incremental dependency tracking. Not working yet.

`build.py`: toy example build steps built out of the other parts.


Handling file systems
---------------------

The system tries to treat file systems as a content-addressable store as
much as possible: a 'Blob' is just a sequence of bytes which can be found
from its hash; a 'Tree' is a list of named entries, each either a Blob
or a Tree, and also retreivable by its hash.

This is the same scheme git uses for storing objects; the only difference
is the actual hash algorithm (sha2 vs. sha1) and some details of encoding,
so that we can hash and serialize arbitrary objects.

### Where blobs get stored

- Non-blob objects and some blobs are stored in a dbm database.
- Blobs that came from files can be stored directly as files, instead of requiring the bytes to be read into memory and then serialized out again.


Dependency tracking
-------------------

Suppose we have a very large source tree, and compile some file 'foo.c' that
depends on a few headers:

    obj = compile_c('foo.c', source_tree, opts)

This will work, but if source_tree is very large, it won't be useful: changing
any unrelated file in source_tree will trigger a recompile. We only want to
recompile if a file actually used by foo.c changes.

A file system then be thought of as a function from a path to the contents of the
file at that path. To make examples simpler and more general, we'll replace the
filesystem with an arbitary function.

I.e., we want to memoize:

    output = step(normal_args, f_arg)

Where normal_args can simply be content hashed, but for f_arg we don't want to include irrelevant parts of the definition in our hash.

Suppose this is our step function:

    def step(f):
        x0 = f(0) + 1
        x1 = f(x0) + 1
        x2 = f(x1) + 1
        return x3

    assert step(lambda x: x) == 3          # x0=0+1; x1=1+1; x2=2+1
    assert step(lambda x: x % 10) == 3

`step` evaluates `f()` at three points. We pass in two different definitions
for `f`, but since `step` never uses the parts of `f` where they differ it
doesn't care.

Note that the first access must always be to `f(0)`. Regardless of the definition of `f` we pass in, the first access can't depend on it, because we haven't used `f` yet.

Let's replace `f` with a magic object: it stores a finite set of points, and when
evaluated at a new one, it causes the expression to yield the argument to f, and
we'll resume (or try again) with that added:

    step({}) -> yield(0)
    step({0: 0}) -> yield(1)
    step({0: 0, 1:1}) -> yield(2)
    step({0: 0, 1:1, 2:2}) -> 3  # done

Now we have something we can memoize.


Generalizing to multiple functions
----------------------------------

If `step` takes two functions (f,g) and interleaves calls to both, we can
model it as a single function that takes `Either f_arg g_arg` (and so on for
any number of functions.)


But C++ compilers suck
----------------------

Unfortunately, this depends on knowing the dependency order among accesses.
E.g. suppose we're compiling `foo.c`, which always includes `foo.h`, which
may or may not include `bar.h`.

But the compiler just outputs an unordered bag of dependencies.

We can address this by incrementally refining the memoized result if later
calls record different dependencies.

clang sucks slightly less; it has "-Xclang -dependency-dot" which can output
almost the true deps. Except it doesn't output anything for *missing* deps that
cause errors.

Also none of them output anything for `__has_include()`, which makes the
generated deps kinda useless.

Also it would be nice to be smart about which #defines are relevant or not,
so changing a define wouldn't cause a recompile if it was never used.
This starts getting into a custom C++ preprocessor though. (Maybe that would
be useful to ship as a standalone tool? Then it could be written in Rust
and be fast and get support from other people who found it useful, and also
maybe it already exists.)


TODO: Minor improvements
=========================

Allow an existing git object store to be used for file backing, why not?
- Need to either use git's algorithm for blobs, or keep an extra mapping.

- Back hash store with sqlite or something

Hmm: is there any reason to have 'Blob' separate from 'Sig(bytes)'?
Seems like they're pretty much equivalent, both hashes of some bytes
plus a convenient way to materialize them.

...
Could gain some efficiency via special hashing for set-like (unordered) objects.
Especially if we can compute hash(a+b) from hash(a)+hash(b)
Set: add #'s together mod (2^255-19)
- but need to watch out for (re-hash) short byte hashes: easy to forge sums.
- special 'ListHasher' keeps digest internally, allows incremental append
- special 'SetHasher' allows incremental add/remove


FS partial tracking magic
=========================

Or to prevent final result from depending on access order:

    A0 = hash of call and args
    Y0 = hash(A0, {})
    y[Y0]: set of "first" accesses from Y0
    S1 = S0 | y[Y0]
    Y1 = hash(A0, f . S1)
    S2 = S1 | y[Y1]
    Y2 = hash(Y1, f . S2)

Problem:
- Y1 contains hash of some old fs subtree.
- If we have to split S1 into S1a and S1b, then we need to find Y1a and Y1b too.
- Could just not do it. We'll do some extra work if we go back, but it will eventually converge to the true order.

    actual order: a,b,c,d
    old memo:

        memo(A, {}) -> Left{a,b,c,d}
        memo(A, {a:A,b:B,c:C,d:D}) -> R

    new memo: f(b)=B1, f(d)=D1, order=a,b,d -> R1

        memo(A, {}) -> Left{a,b,d} # not sure about c yet
        memo(A, {a:a,b:B,d:D}) -> Left{c}
        memo(A, {a:a,b:B1,d:D1}) -> Right(R1)

    problem:

        how do we find hash of {a:A,b:B,d:D} when we don't have B or C any more?
        can we do set magic?
            hash({a:A,b:B,d:D}) = (h(a,A)+h(b,B)+h(d,D))
            we have:
                hA + hB + hC + hD
                hA, (and useless hB1, hD1)
            we need:
                hA + hB + hC
        no, so need to deser the actual list. Fortunately just hashes,
        not contents.

    ...
    Nice to not depend on access order, but now we're getting
    back increasingly large sets to check; have to check stuff
    multiple times, not necessarily a win. Both otherwise we have
    to rewrite a whole tree if we split near the root so need this way.

    memo 1:
        arghash -> access list | result
        (arghash, f[access list] -> access list | result

        def get_memo(Y, fs):  # Y = hash of call and args excluding fs
            while True:
                ks = y[Y]       # Either Right(result) or Left(points)
                if ks.is_right():
                    return Some(ks.right)
                Y = cas.sig(Y, {k: fs(k) for k in ks.left})


Efficiency of Yoneda thing
==========================
Problem:

1000 files divided into 10 dirs of 100 files.
100 libs, 10 per dir, each dependent on random subset of files in that dir
Each lib depends directly on 0-2 other libs (topologically sortable)

As I have it now, the top-level project depends on all the files. After we
check it we have to check again for each sub-thing. (Maybe not *so* bad).

- Not taking advantage of FS tree shape at all. (Sort of: if say the source fs we pass in is only a subtree, can do a memo on the complete tree in addition to subset.)

Can we take advantage of the fs tree shape?
1: pass around subtrees of the fs where possible, so normal memoization catches it as long as that subtree doesn't change.
2: when we memo (f(x)->partial y), also do a version with y->y' where y' is the parent directory of y. (So instead of saying "access file a/b/c", it's saying "access files in a/b")

Can we take advantage of the call tree shape?
- partly happens automatically? If lib appears at 10 call paths from the root, after the first one is checked, the rest ...?

    {a/x/1} {b/x/2} {a/y/3} {b/x/4} {b/y/5} -> R
    {a/x} -/
    {a/x} {b/x} {a/y/3} {b/y/5}
    {a/x} {b/x} {a/y} {b/y/5}
    {a/x} {b/x} {a/y} {b/y}
    {a} {b/x} {b/y}
    {a} {b}

end up with N^2 nodes, no good
- since we have the whole list, we can apply any compression we want to it
(e.g. merge X nodes into a larger node)
Anyway this seems solvable with more heuristics, but possibly it's not necessary.



Random conveniences
===================

Every intermediate directory gets a "WHAT.md" file explaining to humans exactly what is in there and why.
Or a "WHAT.json", plus a tool to format it for readability. (But first line of json must point to the tool
for human readers.)


William
=======
Cmake - properties on targets are nice

some steps want to e.g. mutate the filesystem

- guess that's ok, just need to be careful about not sharing their inputs

- yes: run_tool normally generates a fresh output dir. If you want to stomp on an old one instead that's fine, just avoid constructing allegedly pure refs into it.


Working out cases
=================

    cxx_library(
        name = "blas",
        srcs = ["blas.cpp"],
        public_headers = ["blas.h"],
    )

    # in this case, the deps are just a string.
    # what if there's a USE_BLAS option?
    cxx_binary(
        name = "fred",
        deps = [":blass"]
    )

    # in this case, the deps are just a string.
    # what if there's a USE_BLAS option?
    fred = lambda use_blas: cxx_binary(
        srcs = ["fred.cpp"],
        deps = [":blas"] if use_blas else []
    )

Do options apply to the target, or to the module containing them?
Let's make it the module:

    eigen = cxx_library(
        srcs = ["eigen.cpp"],
        deps = [":blas"] if options.use_blas else []
        defines = ["EIGEN_USE_BLAS=1"] if options.use_blas else []
    )

A target consists of:
- a path string
- a dictionary of options

    def with_options1(t, **opts):
        if type(t) is str:
            yield Ref(path=t, **opts)
        else:
            yield Ref(path=t, opts={**t.opts, **opts}

    def with_options(*targets, **opts):
        return [with_options1[t] for t in targets]

    def host(t: str):
        return Ref(t, **host_opts)

Suppose we have some library that we may or may not want to use:

    cxx_library(
        name = "blas",
        ...
    )

Other libraries might have config knobs to use it:

    import options.use_blas

    cxx_library(
        name = "eigen",
        srcs = ["eigen.cpp"],
        deps = [":blas"] if options.use_blas else []
        defines = ["EIGEN_USE_BLAS=1"] if options.use_blas else []
    )

Further downstream, we have a lib that's implicitly affected by the eigen choice:

    cxx_library(
        name = "ceres"
        deps = [":eigen"]
    )

    Even though ceres doesn't mention any options, it's affected by some.
    Simliar for e.g. target arch - of course everyone doesn't specify that!

    Back to blas flag, there are possibilities here:
    - The option in eigen affects its clients, so we need two versions of ceres too.
    - The option in eigen is internal-only, so we don't.

    Eigen needs to be explicit about whether the ceres option is transitive to
    other libraries. (Of course it's transitive to the final executable).
    [Maybe this can fall out of exactly how include vs. link deps work?]

    - If a target actually comes out identical, we might merge it after running the module twice; that's ok.
    - Eigen/blas case: if some option changes an exported preprocessor flag of eigen, then that affects dependent libs.
    - If it only changes linker flags, it doesn't.

Now suppose we want two versions of some binary, with and without blas:

    cxx_binary(
        name = "program1",
        deps = with_options(":ceres", use_blas=True)
        ...
    )
    cxx_binary(
        name = "program2",
        deps = with_options(":ceres", use_blas=False)
        ...
    )

Different example: target that requires running some tool on the host.

    cxx_binary(
        name = "spaminator"
        ...
    )

    run_host_tool(
        tool = host([":spaminator"]),
        args = ["--make-spam"],
        ...
    )

Problems:
- If options come from magic includes, they affect all targets in the buck file which we may not want. But as long as I can write:

    if options.flag1:
        x = 3
    else:
        x = 17
    ...
    cxx_library(deps = [a] if complicated(x) else [b])

then this is inevitable. Lambdas or something could address this anyway, don't worry about it yet.
(Also, we could run the definition twice and then notice that they came out identical.)

Ideally, we wouldn't have to worry about this: just merge targets that actually come out identical,
and let optimization / program transformation avoid the double eval.

Look at where it comes together:

    def cxx_binary_target(name, srcs, libs):
        objs = cxx_compile_target(srcs[i] for i in srcs)
        cxx_link_target(name, objs, libs)

We need to actually follow the targets to know things like our compile flags.
Ignoring for now when exactly this happens, what do we need from target?

Say there are two cases: USE_BLAS is or is not exposed from Eigen's headers.
This will show up as either:
- blas being a public dependency of Eigen, or
- eigen defineding some public_preprocessor_flags

Now ceres has a public dep on Eigen. So when we resolve ceres (from the 'use_blas' final binary):
- ceres' options include use_blas, though it doesn't look at that
- so ceres references Eigen via `ref(":eigen", use_blas=True, ...)` 
- that reference is being resolved by the cpp_lib implementation, so it knows it just wants the headers info:

    resolve(ref(":eigen", use_blas=True, ...)).exported_preprocessor_stuff

resolve() will make sure Eigen's module has run, and get a cpp_lib resolved target.
[getting confusing. Remember pure functions...]

* cxx_library() et al are defining pure functions from their explicit args, plus an implicit options arg,
    to the set of outputs produced.

* resolve(target) partially evaluates that function, giving a new object where irrelevant options have been discarded.
    * this is the point where we can do equality checks to see if things that looked different are actually the same
    * although actually we logically always do that on everything

    def resolve_cxx_library(lib):
        # assume for now these are all cxx_libraries too
        deps = [resolve(t) for t in lib.deps]

* resolve() actually returns the same object, just partially evaluated. So logically we don't even need it, except to make it explicit when we move to a phase where it's allowed.

* `mylib.compile_deps` is some function of mylib, which only depends on some of the options...

    def cxx_compile_deps(target):
        for dep in target.deps:
            return dep.{
                defines,
                include_dirs,
                ...
            }

Ok what's actually needed to build a simple cxx lib?

    - sources
    - include dirs
    - preprocessor flags
    - general compiler flags

single cxx obj:

    - source
    - include dirs
    - preprocessor flags
    - general compiler flags

class cxx_obj:
    # deps of a cxx_obj are mostly libraries with include dirs,
    # and possibly with exported flags
    def __init__(self, src, deps, defines, options):
        ...

    def compile_flags(self):
        return merge_flags(
            dep.exported_compile_flags for dep in deps,
            self.private_compile_flags)

    def cxx_obj(src, libs, options):
        # rule to build a single cxx object file
        # compiler -- compiler as a host command target
        all_compiler_flags = merge_flags(lib.exported_compiler_flags for lib in libs)
        run_tool(
            tool = "//tools/cxx:compiler",
            args = ["-c", source_location(src),
                    *cat(['-I', lib.include_dir] for lib in libs)
                    "-o", output_placeholder(ext=".obj"),
                    *all_compiler_flags
                    ]
        )


What is a target really?
------------------------
I want it to be a pure function from inputs to outputs. But there are also things like
lib include dirs etc.

So, e.g. a cxx_lib target is:
- a pure function from args, options, and referenced targets to a cxx_lib object, which is a compound object containing:

    - the actual generated lib file
    - any error messages and warnings produced along the way

So abstracting a bit:

- A target is some representation of an unevaluated function (as a closed expression) to a set of outputs
- inputs are plain values and references to outputs of other targets
- reducing a target consists of:
  - see if it's cached; if so, done
  - otherwise, run a target-specific fn which may produce outputs, or may produce a subgraph of targets which eventually produce the output.

So e.g. running the compiler: first node pulls out whatever options it cares about, builds command line, returns node that actually runs the compiler.

Evaluated nodes:
- Correspond to one of:
  - FAIL
  - path to a generated file on disk
  - path to a generated directory on disk
  - path to a source file
  - literal (e.g. string, int)

Compound:
- contains a list of sub-nodes
- sub-nodes can be requested by name (simple string)
- "list-of-sub-node-names" is just another sub-node

Warnings / metadata:
- either every node has them, or they're built 

Whan can we do with a possibly-unevaluated node?
- Request a sub-node from it, if it's compound. `node.get_output(name)` 
- Request a final value of some expected type.
- Get a hash of its inputs
- That's all we need?

How are common tools referenced?
--------------------------------

In the cxx_obj tool I had `tool = options.cxx_compiler`, implying that options can
contain target refs. However this could be done a different way, say:

    tool = "//common_tools/cxx:compiler"

And then that target would use conditionals on its own options to point at clang or
gcc or whatever.

Differences:
- In the first case, you can't even really guess what all the deps are unless you have some knowledge of the options. So it's a more open world. This is good for extensibility, bad for static analysis.
- First case might open up other bits of trickiness. Or might not.

Do we need to get right down to obj file to know whether "O2" and "Omax" are the same?
- maybe; if so we could fix perf by caching both.

    # rule to run the tool at `path` on the host machine
    # all tools must:
    #   - have fully deterministic outputs for for given inputs
    #
    # when the tool runs:
    #   - if output is a single file, 
    #   - current directly will be a gen dir for output
    #   - all outputs should be placed in that dir
    class preinstalled_host_tool(Rule):
        def __init__(self, name, path, env, args, single_file_output=False):
            ...

        def outputs(self):
            return 
...

Building up from the bottom:

pure python rule: output is just a string

    def pure_fn_rule(func, *args, options, **kwargs):
        return func(*args, options=options, **kwargs)

run a shell program that produces only stdout:

    # other_files_to_watch is a list of programs
    # which may affect the behavior of main program
    def shell_rule(program, files_to_watch, args):

Logically correct hashing
-------------------------

Common case, e.g. with compiler:
* we don't know before running the tool which files it will access, but we do find out after.
* overall fs could be quite different, doesn't matter as long as ref'd files are the same.

First problem, avoiding double-build: no problem! The way we get the list of referenced files
is by invoking the compiler, so if we if we have the list we're good, and if we don't have
the list we're good.

Almost: except we're caching an overly-specific case. Something something Yoneda lemma.

And what if we have twenty lists of referenced files, differing in headers that we don't
know if they're relevant or not?

Take the stuff we know we need (compiler version, flags, primary source).
Define a function "first-dependency" from that stuff the the first fs reference.
Or, to generalize: a function "next-dependency" from (compiler version, flags,
primary source, list-of-accessed-fs-paths) to the next fs path to add. (Or to a
*set* of fs paths to add; we can do a breadth-first search here and end up with
a tolerable number of steps.)

Unfortunately that isn't a great match for what the compiler actually gives us?
E.g. if it just outputs a flat list of deps. We don't know which deps are directly
implied by the primary deps, and which aren't. [But compiler dep files are stupid
and broken anyway, so might as well just act as if they don't exist.]

- Assume that we *can* detect ordering properly, even in tricky cases like

    f1: include A
    f2: include B
    f3: ifdef something
            include C
        endif

    We could even cache stuff like:
        <file-blob> -> {known include paths}

Anyhoo. How do we map this to the fs-may-have-confounders problem?

    def compile(src, full_fs, options):
        open = {src}
        fs = full_fs
        while open:
            open = {scan_for_includes(full_fs[f]) for f in open if f not in fs}
            fs = fs | open
        # at this point, fs is a minimal view of full_fs 
        referenced = actual_referenced_files(src, fs, options)

    # can't *just* scan for includes; we need to do preprocessing too
    # and it would be nice to examine a minimal set of defines, just
    # like we examine a minimal set of files.
    def scan_for_includes(src, full_fs, options):
        open = {src}
        fs = full_fs
        while open:
            open = {scan_for_includes(full_fs[f]) for f in open if f not in fs}
            fs = fs | open
        # at this point, fs is a minimal view of full_fs 
        referenced = actual_referenced_files(src, fs, options)

Well if nothing else, this sure gets tricky. Can we yoneda lemma this thing somehow?

- Say 'fs' is a special kind of object that tracks attempted references to it.
  (ideally some kind of linear types would help us keep this straight).

we have f(g(a)), f(g(b)), a != b, but possibly g(a)==g(b). (f is compile, g is 'relevant subset for f')

Might be better if this could be automatically traced somehow:

    def scan_for_includes(src, fs, options):
        # could write this recursively instead of iteratively if that would help.
        # but want to make both patterns work.
        open = {src}
        found = {src}
        while open:
            open = {scan_file_for_includes(fs[f]) for f in open if f not in found}
            found |= open
        return found

Yes! General version.

Consider only the sequence of accesses to fs[f].
- We know that the first access will be the same regardless of fs, because we haven't looked at it yet.
- We know that the second will be the same conditioned on the first, etc.
However, this is linear: we need to separately memoize the next access for every access. So just
checking that nothing happened is also linear.
- We can fix that the same as before and stay generalized, by giving fs a function from sets of paths to sets of files. So the scanner now has a way to indicate a lack of dependencies.

Syntax rewrite:

    {f(a) for a in x} -> {f.__map_set__(x)}     # observe parallelism where possible

So what exactly are we caching here? Given `scan_for_includes(src, fs, options)`:

    during evaluation it makes a sequence of calls to fs[paths]
    we want to cache:
        scan_for_includes(src, fs, options) -> actual result
        accessed(scan_for_includes, src, <null-fs>, options) -> <fs-1>
        accessed(scan_for_includes, src, <fs-1>, options) -> <fs-1> | <fs-2> etc.
        scan_for_includes(src, fs0, options) -> actual result, where fs0 = limited view of fs

Then on a later call `scan_for_includes(src, fs2, options)`:

    if there's an exact match on fs2 that's nice. Assume there isn't.
    It walks a chain of accesses. Actually we probably don't need to store them all in order:
    need to walk the chain anyway right?

Ok so this seems solvable but is a distraction. It's fine to be a little conservative on re-scanning includes anyway.


Mutation
========

Disallow it initially. Skylark-style limited mutation should be ok but
will require lots of thought that I don't want to think right now.

..

Deps tracking API
-----------------
The underlying logic is pretty simple, but mapping to mutable FS operations
and command invocations in a way that isn't error prone is tricky. Could use
a FUSE filesystem to make it better, but assuming we don't do that:

Underlying model
----------------
Asking for a tracked dep is like an algebraic effect; it could be rewritten as returning a read request plus a continuation, followed by the continuation being called with the result of that request.

So also could be viewed as a Python 'yield' or 'await', although we (probably?) don't want to implement it that way.

Is there any advantage in explicitly implementing via yield or await? Yes:
- Actual memo machinery is just normal pure fn stuff, no back channels.
- Indicating serial vs. parallel deps is done via standard Python utils

Disadvantages:
- Feels very clunky
- Since the leaf routines use async, *everything* will end up marked async.

Could probably do just as well with normal fn calls, just keeping the async/yield model in mind.

...

So with the yield / effect view in mind: what does dep-tracking look like?

- There does need to be some type which represents the "effect sans handler", e.g. an fs tree with not-yet-known contents.
- When we have a fully known tree: first apply simple memoization, then rewritten.

i.e.

    f : x:Whatever t1:Tree t2:Tree -> int
    f = let a = t1 'a'
            b = t2 'b'
        in g a b

check if that is memoized as-is; assuming not, call rewritten version:

    f : x:Whatever ot1:OpaqueTree ot2:OpaqueTree -> int
    f = ReadReq ot1 'a' \a ->
        ReadReq ot2 'b' \b ->
        g a b

The opaque arguments must be identified by position, so that the outgoing 
calls look different even if the same value is passed for t1 and t2.

When we don't have a fully-known tree (e.g. starting with a source dir), what do we do?

- Currently have types Path / Blob / Tree. Blob and Tree act like values.

Tree or Blob: when passed as arg, already introduces a dep on entire contents

src path:
- acts like a string
- introduces a dep on just that path (stat, not contents of dir)
- use contents() to convert to tree if dep on the whole tree is preferred
- buck etc.: default is tree constructed from explicit includes etc., middle ground. Could do the same. Autodeps are always for performance, never correctness.

OpaqueTree
----------
Not sure if I really need this or not?
- It represents a tree but with not-yet-known contents

- Might be redundant with Path or Tree? Certainly they can do all the same
  operations, so difference is just one of intent for memoization. Path
  represents just the path itself (semantically not much more than a string);
  OpaqueTree means the same thing a Tree but is lazier about storing contents.

Definitely shouldn't merge this with Tree, because Tree is a much simpler
concept. It's just a data structure, even simpler than json.

Might make sense to merge with Path, since otherwise Path is very error-prone
to use. Also Path is mostly used as a relatively high-level object.

Difference from Path comes with hashing, but since the question is all about
exactly what hashing means, and that's not 100% clear for Path, ok.

- Still want to have the (Tree,string) kind of Path. It's fine as-is. But maybe that becomes the only kind?

Ok, I think Path just needs a few more knobs:
- A source or gen path can be rooted under another path (i.e. three components: general category, tree root under that general category, path into tree.)
- It must be possible to distinguish paths at different arg positions. Probably need to be compatible with some general mechanism for this. What happens exactly if we can't? - call 1 with (A,A) records a bunch of uses of A; now what should call 2 with (A,B) do? - might be able to just distinguish these cases at entry to memo and then have them be different. Or not.

So, new Path type:
- logically it models a pair of functions (stat: str->Stat, get: str->(blob|list[str]|None)).
  Can also define a subtree function:

        subtree(parent, rel) = {
            stat: \s -> parent.stat(join(s, rel))
            get: \s -> parent.get(join(s, rel))
        }

- root can be a tree or somewhere under src_root. Not sure about gen.
- doesn't require store, read-only. (Maybe ReadPath vs. WritePath is the relevant distinction).
- can compute hash of tree under this path if desired
- relevant kinds of access: stat result (including missing file) and read

Ok, work on the general function form:

what I call:

    foo(1, 2, [3, 4, (5, {'x': magic_tree_object})]) ?

We need to identify the magic_tree_object all the way inside x there.

But! Fortunately we have to dig into the arg anyway for hashing.
So what does hash(arg) look like for such an arg?

- we have to be able to look at (arg) a know that it's not fully hashed yet
- ideally we could efficiently substitute canonical values for placeholders,
- magic_tree_object hashes to some kind of special positional placeholder
- when we *use* the object, we need to know that we used "object at arg position X" rather than the object itself. Ugh.
- in Python probably can't do that exactly. But as long as objects have different identities, we can instead just hash the f(x,x) vs. f(x,y) cases differently and go by identity from there.

i.e.:
- sig computation when entering the memo creates a list of traced object IDs.
- when an access is recorded, we can track it appropriately.

Ok that works but maybe there's a simpler way (analogy to effect systems again):
- there is only one instance of each traceable object
- logically in fact there's just *one* traceable object, a bundle of those instances.
yeah that works?

so `src_tree` is actually `lambda *args: read("src_tree", *args)`?

...
Maybe this is all too clever. Consider how it works in buck:

- libraries export a relatively small tree of include files
- these are given as inputs to tools, sometimes relative to higher-level dirs
- if using say `-I` high in the source tree, use the simple known list of include sets to filter the tree; can pass the normal path in for `-I`, and just check after the fact that the tool didn't access anything it hadn't declared.

In practice this is better because it's less magical. Dependencies are declared in comprehensibly-sized chunks, errors are legible, magic is not required.

Implementation?
- memoized functions can't just take source path strings as inputs, they have to convert to trees first.
- could auto-convert or error out (former more convenient, latter less likely to produce accidental giant slow builds.)

How do we prevent it? (Strings are ok in general after all).
- function to produce a *new* tree from a source path can't be called inside memoized context?

This would have to be disallowed:

    def my_c_lib():
        return c_lib(srcs=["foo.c"], headers=Tree("include/"))

In favor of:

    headers=Tree("include/")

    def my_c_lib():
        return c_lib(srcs=["foo.c"], headers=headers)

But we want to be memoizing build file processing too; this would forbid it, no?


Implementing autodeps
---------------------
- At memo time: find relevant objects, replace with placeholders "special object #1, #2, ..."
- Can do that with _get_sig() on those objects
- When those objects are accessed, they add dep to top memo on stack

Is that always right?
- need to add all the way up stack? That would suck.
- but it is necessary: the top level really does depend on a zillion files.
- so there needs to be some way to merge things back together for checking

    def top_level_fn():
        a=big_1()
        b=big_2()
        c=big_3()

- so top_level_fn ends up depending on 1M files
- even the dependency list is pretty big
- really is better to lump things up a little, e.g. make it depend on 1000 trees of 1000 files.
Going to rerun it almost every time anyway.

If we do that:
- build files get as an input a *Tree* of their associated files, which they can *explicitly* depend on.
- special dep-list stuff only applies to cc files that need it

    def load_build_file(path):
        bftree = make_source_tree(path) # not memoized but can be special-cased
        funcs = load_module(bftree["BUILD"]) # memoized
        return funcs

    problem: there might be super high-level build files; don't want them to depend on the world
        - could copy blaze and exclude subtrees with their own build files
        - maybe it is ok to run all build files? but I really don't wanna.
          - caching build files requires serializing functions? better to avoid that
            - not if we say that cas lookup failure for a memo result makes us rerun the memo

ok how bad is this -
- we have a giant set of file deps under the top-level target
- but if we represent it as a tree, most leaves will be the same as in subtargets
- ok, how do we represent it as a tree?
  - we just use a tree as the data structure for a set of paths and it just works. sweetzorz.

So there does need to be a `FancyTree` type which covers other FS operations:
- explicit file-not-found indication
- explicit "did I do a listdir here?" repr
  - what about globs? e.g. someone looking for `*.h` doesn't care about new cpp file
  - don't worry about that yet
- not sure if it makes sense to have a single `Tree` with more features or two kinds
- trees can be merged, have to be careful about globs though
- important to keep the mapping to/from pure functions in mind to avoid screwups.

merging trees:

    def merge(t1, t2):
        if t1 == t2:
            return t1
        if not isinstance(t1, TreeSlice) or not isinstance(t2, TreeSlice):
            raise BadMerge

        if t1.is_full:
            # check that t2 is compatible


        for k in set(t1.keys()) + set(t2.keys()):
            if k not in t1:
                if t1.is_full:
                    expect(k is None, BadMerge)
                else:
                    out[k] = t2[k]
            elif k not in t2:
                if t2.is_full:
                    expect(k is None, BadMerge)
                else:
                    out[k] = t1[k]
            else:
                out[k] = merge(t1[k], t2[k])

        return TreeSlice(out, is_full = t1.is_full or t2.is_full)

this handles everything except globs. How do those work?
- just one flag, "did I do a listdir". If it's set, list of non-None entries
is complete, and no Nones are required.

    def rel_path_to_treeslice(rel, contents):
        if rel:
            parts = rel.split("/")
            for part in reversed(parts):
                contents = TreeSlice({part: contents}, is_full=False)
        return contents

    def path_contents_to_treeslice(path):
        contents = path.contents(allow_missing=True)
        if contents is None:
            while path.parent().is_missing():
                path = path.parent()
            assert path.contents(allow_missing=True) is None
        return rel_path_to_treeslice(path.rel, contents)

Ok this can be made to work, but has significant complexity. But hopefully the
memo correctness falls out of lower-level mechanisms.

Globbing could be fancier, e.g. could track not just 'is_full' but which globs were done.
Then it's ok to combine with any files that don't match those globs. Probably not a win
though. Unless it is.

"fileset" might be a better name than "treeslice". Or "lazytree"?

Pure fn version?

    compile(srcname, srctree, [inctree1, inctree2])

srctree, inctree1, inctree2 are empty lazytrees with fspaths
    each corresponds to a function:
    
        subpath,get? -> isnone|isblob|isxblob|isdir if get? is False
                     -> None|Blob|XBlob|[names] if get? is True

the y_memo stuff wants to track an abstract set of keys at which fn was evaluated, and values produced by that. If compiler was looking for "a/b/c/f.h" and found it in inctree2, what does that correspond to? Maybe it's better *not* to work with this explicit tree structure, and just compress a set with lots of common prefixes?


srcname can be just a string
compiler tells us that output depended on some list of absolute paths
we can map those to somewhere under srctree, inctree1, inctree2 - this produces three non-empty lazytrees

anyway, should look like:

    inctree1: !exist a/b/c/f.h
    - which I can't actually represent if (say) b is missing.
    - maybe the right thing to record is `search(t1,t2,"a/b/c/f.h") -> t2/a/b/c/f.h` so we can track the semantics more directly?

how would that work?

    def f(g, h):
        compile(g, h)

logically, compile() should have been:

    def f(g, h):
        compile(\s -> search(s, [g, h]))

where search() is something the memo system can do itself

anyway this is all getting horrifically tricky. Is there a better way?
back to just regular memoization, no yoneda magic
for the compiler case:
- memoize based on the full tree
- changed one irrelevant file? memoization will fail
- compile code has special logic to deal with that explicitly

    @memo
    def compile(src, srctree, [inctrees]):
        callsig = (compile, src) # = memo.top() or something
        out = check_y_deps(callsig, lambda i: )
        if out:
            return out

        cc_out = run_tool(["cc", etc])
        deps = cc_out.tree["deps.d"]
        real_deps = deps_to_named_file_set(deps, src, srctree, [inctrees])
        record_y_deps(callsig, real_deps)

well that's a whole lot simpler. Doesn't work in as many cases: higher-level
code will still call compile() when nothing's really changed, but that's probably
better than having it depend on a million things.

Big advantage: if you do nothing, it's still correct, just rebuilds more often.

...

Ergonomics in build files and current location:

- Make 'here' an explicit param. Not unreasonable (e.g. 'self' in Python)

Anything else already involves magic, but maybe not so bad.
- make 'here' a global, look in bytecode for free names, then treat as argument

If we want to use simple string names for paths, e.g:

    def mylib():
        return cxx_lib(srcs=["foo.cpp"])

then cxx_lib has to know what tree we're in.
- cxx_lib could be a parameterized import
- or mylib() could be implicitly wrapped in a dynamic variable thingy?

Nope:

    def xlib(s):
        return cxx_lib(srcs=["foo.cpp", s])
    # <other build file>
    def mylib():
        return other_module.xlib("bar.cpp")

Better to use explicit Tree param.

Ok what about implicit global `loc`?
- problem now is that it's hard to know if it's used or not
- need to follow global references
    - actually that's already covered by fn hashing!


Source control integration
--------------------------
Super important to be able to reference other packages, and have the build system fetch and build them out of tree.

*Possibly* these references can be git subrepo links. That would be nice in a couple of ways:
- (some) people already know how to use it
- How to use a patched subrepo is obvious (if the subrepo is materialized, just use it as found). Though this gets tricky if the same subrepo is referenced from multiple places - need to explicitly say what we want in such cases.
