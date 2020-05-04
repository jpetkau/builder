proper build system w/ python-like config? (No partial eval)

- py functions are just normal functions
- build tree is exactly ordinary call tree. Lots of memoization.
- no magic laziness, but explicit laziness is ok
- no magic parallelism, but explicit parallelism ok


Minor improvements
==================
Borrow another bit from the hash to mark whether objects are deserializable
or not? (bytes / serialized object / one-way hash).
[Not critical but better to know sooner than later.]

[Easy to compute, it's just the union of 'no-deser' bits on subobjects]

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
- won't always be able to do yoneda thing. Is there another way?

  - just sort accesses. Prev logic: "one of the accesses must be first". New logic: "one of the accesses must be smallest." - no, not the same: the important part was that with the yoneda thing, the first access is unconditional on the rest, so we can store just the one and retrieve it deterministically.

- not as pure but could do some hack to figure it out as necessary. E.g. store the full set for the first call; on next store, extract "first" set as

    {k: k ∈ (s0.keys & s1.keys), s0[k] != s1[k]

    Y0: hash of current call's args, excluding fs
    y[Y0]: set of "first" accesses from Y0
    Y1 = hash(Y0, y[Y0])
    Y2 = hash(Y1, y[Y1])

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


Efficiency of yonda thing
=========================
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

Layers
======
1. Hash-based serialization system so we can recovered stored values.

Plan so far
===========

Hashes:
- All values are represented by content hashes
- Functions are values too, hashable the same way
- Most values are lazy. Hash is the same whether it's evaluated or not.
- Content hashes are trees, so retrieving the value is generally shallow.

Memoization:
- Given a function `f` and args `args`, we store a map from `hash(f,args)` to `hash(f(args))`.

Yoneda stuff:
- For things like filesystem or options inputs: some functions return an additional argument, a list of sets of 'accesses' to the fs or options, along with results. The memoization logic trusts that this list is accurate, and will reuse a memoized result as long as inputs agree at these points. (Note that when this mechanism is used, the *first* entry in the list will be independent of the actual filesystem.)

- To make it easier to collect access lists, memoized functions can be have an implicit return value. The memo machinery knows to check this on entry and exit from memo-ed functions.

Pseudo-nondeterminism:
- Everything is assumed to be pure and determinstic by default. For unavoidable but harmless nondeterminism (like a compiler that sticks a date in its output), functions or values can be marked to prevent spurious warnings.

Random conveniences
===================

For stuff like compiler flags, portable vs. clang or msvc-specific:
- maybe in addition to strings, allow special placeholder objects like "cflag.opt(2)" which are late-expanded?
- or maybe "cflag.opt(2)" is just a regular option? ("options.cflag.O2")
    - that's kinda nice: if, say, O2 and Omax are the same for some compiler, then we merge targets for free?

Every intermediate directory gets a "WHAT.md" file explaining to humans exactly what is in there and why.
Or a "WHAT.json", plus a tool to format it for readability. (But first line of json must point to the tool
for human readers.)


William
=======
Cmake - properties on targets are nice


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

...

Logically correct hashing
-------------------------

    we have g(f(a,b))
    let c=f(a,b)
    should be the same regardless of how c was obtained, so
    we need c's actual hash.

    def eval_to_hash(f, args):
        input_hash = hash(f.hash, x.hash for x in args)
        output_hash = fn_db.get(input_hash, None)
        if output_hash:
            return output_hash
        else:
            output = f(args)
            fn_db.put(input_hash, output.hash)

    def cached(f):
        def g(*args, **kwargs):
            input_hash = hash(f.hash, *(x.hash for x in args), **{k: v.hash for (k,v) in kwargs.items()})
            output_hash = fn_db.get(input_hash, None)
            if output_hash:
                return output_hash
            else:
                output = f(args)
                fn_db.put(input_hash, output.hash)
        return g
...

be nice to specify everything in terms of pure fn calls.
most functions return lazy views of their actual output
can use `await` when we need actual value for a conditional or whatever

Ok:

    run_tool:
        executable
        arguments
        other input files / directories (location relevant or not)

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

Pure fn nodes again
-------------------

Most fns return an object representing the eventual result that acts a lot like a future.

Operations on that object are like chaining futures:

- `obj.x`, `obj.f(y)` etc. usually just returns a lazy wrapper to get obj.x later
- it should early-out on errors, and early-return if obj.x is actually available, but this isn't critical.
- when we actually force obj.x (which can maybe be spelled 'await' in python): something something.

Ok, say we have this:

    def f4(o):
        if await o.x:
            return obj(x=o.y)
        else:
            return obj(x=o.z)

    obj1 = obj(x=f1(), y=f2(), z=f3())
    obj2 = f4(obj1)

    obj1.x - can immediately return f1()
    obj2.x
        lazy
        if awaited, forces obj1.x. Is there a case where we wouldn't also force the next term?
        - nah.

Kinds of things:

- Target reference: ref to some generated object
- Logically, generated files and dirs are just tree-shaped values, even if they're manifested on the fs.

    class FSObj:
        ...

    class FSTree(FSObj):
        entries: Dict[Name, FSObj]

    class FSFile(FSObj):
        data: Blob


Non-caching view
================

What can it look like with no caching at all? (Imagine perfect magic caching under the hood).

    # my_build.yob
    lib = cxx_library(
        srcs=["lib1.cpp", "lib2.cpp"],
        deps=[root.third_party.json]
    )
    prog = cxx_binary(srcs=["main.cpp"], deps=[root.a.b.c.foo])

Doesn't look much different really.

    def cxx_library(srcs, deps, private_flags, public_flags, public_only_flags):
        my_flags = combine_flags(public_flags, private_flags)
        objs = [cxx_obj(x, flags=my_flags) for x in srcs]
        return obj(
            lib=cxx_ar(name, objs),
            objs=objs,
            public_flags=combine_flags(public_flags, public_only_flags),
        )

    def cxx_binary(srcs, deps):
        objs = [cxx_obj(x) for x in srcs]
        bin = cxx_link(objs=objs, libs=[x.
        return bin

    def cxx_obj(src, flags):
        out = gen_dir / util.with_ext(src, ".o")
        return run_tool("c++", src, "-c", out)

    def cxx_ar(name, objs):
        ofile = gen_dir / f"lib{name}.a"
        return run_tool("ar", *[relpath(x) for x in objs], "-o", ofile, output=ofile)

Where does gen_dir come from?
- have options etc. that basically looks like dynamic variables
- can't have per-high-level-target dirs like buck, because sharing is more fine grained than that
- rules should be able to decide when gen_dir is split off, e.g. at lib or obj level or whatever
- assembling a tree view is an explicit rule

Kinds of things:

    Values
    Functions

    `bytes` and `str` are values

    DirEntry = Union[File, Dir]

    class File(Value):
        path: str
        contents: bytes

    class Tree(Value[T]):
        entries: Dict[str, Union[Tree[T], T]]

    Dir = Tree[File]


Resolving Values
================

I'm getting confused by lazy values. Maybe work bottom-up?

1. fully resolved: an actual fully-resolved value [we never actually need this!]
2. unresolved value, with a function that does some work resolving it.
3. partly resolved value: e.g. we know it's a list and the length, but haven't resolved the elements. WHNF.

(1) is the important case obviously. What does that function return?
- either another  partly or full resolved value, or another unresolved value on which progress has been made.

Since I'm so confused here, how about we think of this in terms of expressions.

An expression is:

    - a literal value
    - a literal compound type containing expressions
    - app (fn, args)

..

    def my_func(xs: list):
        return xs[0] + xs[1]

    evaluation:
    - is `hash('call', my_func, xs)` cached? If so, return result of that
    - return Add(Index(xs, 0), Index(xs, 1))
    - 

Mutation
========

Disallow it initially. Skylark-style limited mutation should be ok but
will require lots of thought that I don't want to think right now.


Primitives
==========

For the logical model, probably a good idea to think in LC-style primitives,
explicitly keep track of how that maps back to Python.

Just LC expressions:

    lit X
    var v
    \v.e
    e1 e2

Hashing:

    - actually hash values have MSB=1, then 255 bits of hash
    - inline values have MSB=0, then 255 bits of data following first 1 bit.
    - this allows at least integers and short strings to be represented inline, maybe simple exprs too
    - values are represented by a hash to their contents
    - hashing is shallow
    - need refcounting on trees I guess?

Blobs cannot be self-describing

    enum Expr {
        Lit {value: hash},
        Var {name: &str},
        Lambda {name: &str, expr: hash}
        App {e1: hash, e2: hash}
    }

    # fully evaluate an expression
    fn eval(e: &Expr, env: &Env) {
        match e {
            Lit(h) => DeserValue(fetch h)
            Var(name) => env.get(name)
            Lambda(name, expr) => Ok(Closure(env, name, expr))
            App(e1, e2) => {
                if let Closure(cenv, name, e3) = eval(e1, env)? {
                    let v2 = eval(e2, env)?;
                    eval(e3, env.add(name, v2))
                } else {
                    TypeError
                }
            }
        }
    }

    where does caching go in that?
    - add a flag to lambda whether to memo or not

    # fully evaluate an expression
    fn eval(e: &Expr, env: &Env) {
        match e {
            Lit(h) => DeserValue(fetch h)
            Var(name) => env.get(name)
            Lambda(name, expr, memo) => Closure(env, name, expr, memo)
            App(e1, e2) => {
                if let Closure(cenv, name, e3, memo) = eval(e1, env)? {
                    let v2 = eval(e2, env)?;
                    eval(e3, env.add(name, v2))
                } else {
                    TypeError
                }
            }
        }
    }

    (e1 e2) e3

    - hashes should always be of fully-evaluated eager value trees

So I have:

    g(f("foo/bar", fs), "zoo/zar", fs) -> x
        (looks at "foo", and "foo/bar" if foo is a dir)

I have a hash of all of fs, though it's not that useful yet.

Start evaluating f. It calls (isdir fs "foo"). Need to track that
somewhere right?

Hmm: effect-system CPS or something?

    (f name fs)
    -> GetFS fs "foo" (f2 name fs "foo-contents")
    -> GetFS fs "foo/bar" (f3 name fs "foo-contents" "bar-contents")
    -> "bar-contents"

This works if 'fs' is actually a Unit object placeholder (for hashing purposes):

    hash(f, "foo/bar") -> GetFS("foo", K(f2, "foo/bar", "some other closed-over value"))
    hash(f, "foo/bar") -> App(f2, "some closed-over values", GetFS("foo"))

What if f has multiple filesystem args? The continuation is ok, it will be different depending
on which one we accessed. But GetFS needs to indicate which arg it's talking about?

    GetFS(fs, name, k)

Different view / problem:

    f(a(b(),c()), b(), c())

Can we cache this without evaluating a() b() and c()?

We can cache `eval("expr")` so why not `expr`?
- just to keep things sane. We *can* hash `\() -> expr`.

So: `f(a(b(),c()), b(), c())` has to be evaluated to hash it.

`\() -> f(a(b(),c()), b(), c())` is hashable, and subject to spurious differences under partial evaluation.

Back to mapping to Python again: say we use 'await' for relevant parts

    def getpath(tree, path):
        for component in path.split("/"):
            tree = await get(tree, component)
            if tree is None:
                return None
        return tree # or blob

"await" here doesn't necessarily cause us to wait (that's "force"). Instead
it's a marker for which parts of 'tree' we're using?

What if we didn't do that, and instead just made 'tree' keep track itself?
E.g.

    # 'fs' is just a function from name to Optional[dirent]
    # so multiple fs can be mapped to a tuple of single fs's?

    getpath(tree, path) ->
        accesses = get_access_list((getpath, 0, path))
        for (name, hash) in accesses:
            if fs[name]!=hash:n

        tt = access_tracker(tree)
        out = actual_getpath(tt.fake, path)

        # tt contains some set of accesses
        store_access_list((getpath, 0, path), tt.list)

    def store_access_list(call, accesslist):
        for (i, (args, result_hash)) in enumerate(accesslist):
            store_access((i,args), result_hash)

    def check_access_list(call, fs, accesslist):

General form:
- g(f) = f(1) + 1
- turn this into tail call: g = \f -> f 1 (\r -> r + 1)
- cached at f0
- now we pass in some unknown f1 into same g
- we want to know if we can used cached g(f0)
- initially can't: f1 != f0
- ...

Doesn't match what we really want here

in general:
- for any value passed in as an arg, we'd like to find its equivalence class for hashing
- in general that's not possible. suppose fn. is "x mod y". x's class depends on y and vice-versa

Back up to Python:
- again, hash is always on fully evaluated form
- we can annotate functions for tracing:

    @minimal_dep("fs", "options")
    def compile_cxx(src, fs, options):
        blahblah

    - this wraps the 'fs' arg in something that traces accesses
    - has to work through hashed sub-functions but probably it just will (because the wrapped fs is different than the original)
    - traces need to be a sequence of sets:
      - unconditionally access first set of stuff
      - if they all match, unconditionally match second set, etc.

How dis work:

    # Say fs is a function from a list of paths to a list of blobs or None.

    @partial_access('fs')
    def compile(src, fs):
        paths={src}
        # just hardcode in three layers for now
        paths = {scan(b) for b in fs(paths)}
        paths = {scan(b) for b in fs(paths)}
        paths = {scan(b) for b in fs(paths)}
        tool(...)

    @partial_access('fs')
    def compile_lib(fs):
        obj1 = compile("file1.c", fs)
        obj2 = compile("file2.c", fs)
        return ar(obj1, obj2)

    class PartialTracker:
        def __init__(self, realfn):
            self.realfn = realfn
            self.calls = []
        def __call__(self, *args, **kwargs):
            result = self.realfn(*args, **kwargs)
            self.calls.append(args, kwargs, result)
            return result

- What happens when we pass a PartialTracker into `compile`? Wrap it in another one?
- Say the first compile call has a full exact hash match, but the second doesn't.
- The access sequence of a compile call should be treated as an additional output.

Before we had `f0(fs) -> A`; now we have `f1(fs) -> A,access_list`

Memo lookup logic is straightforward:

    hist = []
    while True:
        a = get_memo('access', f, hist)
        if let Final(value) = a:
            return Found(value)
        hashes = [fs(x) for x in a.paths]
        if a.hashes != hashes:
            # some difference
            return NotFound

Trace capture logic is tricky since there's lazyness all over the place.

- Say the first compile call has a full exact hash match, but the second doesn't.
- access list needs to be part of its return value

So we have a two-layer protocol:
- First: functions can return an access list which the memoizer trusts. They can obtain it in whatever way works for them.
- Second: infrastructure to make it easier to collect said access list.

    @partial_access('fs')
    def compile_lib(fs):
        obj1 = compile("file1.c", fs)
        obj2 = compile("file2.c", fs)
        return ar(obj1, obj2)

becomes

    def compile_lib(fs):
        obj1,access1 = compile("file1.c", fs)
        obj2,access2 = compile("file2.c", fs)
        return ar(obj1, obj2), merge_access_lists(access1,access2)

what happens if we mess up and fail to merge some accesses?
- can set it up so we pass the wrong object into `compile` and get an error

how is higher-level code made oblivious to this?
- memoization wrapper hides this logic from callers

how do we write normal-looking code with this behavior?
- in cases where fs or opts is an implicit argument it might be easier?
- there are implicit return values, just like implicit arguments
- a normal return implicitly merges the implicit returns of called methods
- whether an actual call was done doesn't matter, because they are returned from memoized calls too

So:
- when we enter a memoized function, we set a context
- every time we call a child memoized function, we merge its results into the parent
- this is shallow, so hashes are fine
yeah seems like that should work
main implicit results are:
- list of filesystem accesses
- list of option accesses

How are memo partials actually stored?

  - call to the outer function `f(fs)` stored normally
  - say `f2` is the version of f with an explicit two-arg return value
  - logically: could say that f2() actually returns the first access and a continuation
    - again, would it make sense to actually implement it this way?
    - eh, this is all too tricky. Just store them explicitly.


Affine types
============
Thing that William is big on:
- some steps want to e.g. mutate the filesystem
- guess that's ok, just need to be careful about not sharing their inputs


Lost my Yoneda oh noes
======================

Instead of whole Yoneda thing, what about just tree diffs?
  - all files accessed by program (in any order) represented as a tree, including
    looked-for-but-missing files.
  - take intersection with the tree we actually have, see if it's identical.
  - assuming there are extra files everywhere, this requires checking every dep?
    - except we can cache the intersection computation

    @memo.memoize
    def _deps_match_full(deps, real_tree) -> bool:
        if deps is None:
            # rhs must be missing
            return real_tree is None

        if type(deps) is bytes:
            return type(real_tree) is Blob and deps == cas.sig(real_tree).value

        assert isinstance(deps, dict)
        if type(real_tree) is not Tree:
            return False

        for (k, dep) in deps.items():
            if not _deps_match_full(dep, real_tree.get(dep, None)):
                return False

    def deps_match(deps, real_tree):
        """
        deps is a dict tree which may contain 'None' for known-missing elements
        """
        h = maybe_hash(real_tree)
        if h:
            return _dep_intersection_full(deps, real_tree)

        if deps is None:
            # rhs must be missing
            return real_tree is None
        if type(deps) is bytes:
            # hash of a blob
            return type(real_tree) is Blob and deps == cas.sig(real_tree)

        assert type(deps) is TreeDep
        if type(real_tree) is not Tree:
            return False
        if h:
            return _dep_intersection_full(deps, real_tree)
        for (k,v) in deps.items():
            if v is None:
                return k not in real_tree
            if isinstance(v, Tree):
                rhs_v = real_tree[k]
                if dep_intersection(v, real_tree[k]


real_tree is a tree we may not know everything about
- don't want to evaluate hash at roots if we don't have to, since that
  may touch the whole source tree that we don't care about
- but if we *don't* evaluate hash at roots, what do we do?
  - maybe have a lightweight test if we know the hash or not, use it if
    we have it, recurse down if we don't?

How does this fit into the memo system?
- ah right, that was the problem. We have compile_cxx(src, tree), now what?
- need to know the *unconditional* accesses to tree before we can find
  the conditional ones.

    @memo
    def compile_cxx(src, tree):
        tree2 = filter_cxx(tree, cxx_deps(src, tree2))
        return really_compile(src, tree2)

    def really_compile(src, tree):
        run('cxx' etc)

    @memo
    def cxx_deps(src, tree2):
