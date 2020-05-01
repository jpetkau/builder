import hashes
import fs_store
import mock_store
import fs
import shutil
import sync
import tempfile
import unittest


hash_empty_blob = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391".decode("hex")
hash_empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904".decode("hex")


class TestHashes(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(hashes.hash_object(""), hash_empty_blob)
        self.assertEqual(hashes.hash_tree([]), hash_empty_tree)

        store = mock_store.MockStore()
        h = mock_store.push_dict_as_tree(store, {})
        self.assertEqual(h, hash_empty_tree)

    def test_roundtrip_tree(self):
        store = mock_store.MockStore()
        self.roundtrip_tree(store, {})
        self.roundtrip_tree(store, {"foo": "", "bar": "contents", "": "empty"})
        self.roundtrip_tree(
            store,
            {
                "normalblob": "contents",
                "": "emptyname",
                "emptyfile": "",
                "emptydir": {},
                "somedir": {"a": "astuff", "b": "bstuff"},
                "samedir": {"a": "astuff", "b": "bstuff"},
            },
        )

    def roundtrip_tree(self, store, d):
        h = mock_store.push_dict_as_tree(store, d)
        d2 = mock_store.pull_tree_as_dict(store, h)
        self.assertEqual(d, d2)


class TestPullTree(unittest.TestCase):
    def setUp(self):
        self.fs = fs.FS(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.fs.root)

    def test_pullobject(self):
        dirname = "blerg"
        store = mock_store.MockStore()
        store2 = mock_store.MockStore()
        h = mock_store.push_dict_as_tree(
            store,
            {
                "normalblob": "contents",
                "emptyfile": "",
                "emptydir": {},
                "somedir": {"a": "astuff", "b": "bstuff"},
                "samedir": {"a": "astuff", "b": "bstuff"},
            },
        )
        sync.pull_tree(store, h, self.fs, "blerg")
        self.assertEqual(self.fs.node("blerg").hash, h)

        # This should be a no-op
        sync.pull_tree(store, h, self.fs, "blerg")
        self.assertEqual(self.fs.node("blerg").hash, h)

        # Pull an empty tree to clean out the directory
        sync.pull_tree(store, hash_empty_tree, self.fs, "blerg")
        self.assertEqual(self.fs.node("blerg").hash, hash_empty_tree)

        # This should be a no-op
        sync.pull_tree(store, hash_empty_tree, self.fs, "blerg")
        self.assertEqual(self.fs.node("blerg").hash, hash_empty_tree)


class BaseTestStore(object):
    def roundtrip_blob(self, blob, expected_hash=None):
        h = self.store.put_blob(blob)
        if expected_hash:
            self.assertEqual(h, expected_hash)
        blob2 = self.store.get_blob(h)
        self.assertEqual(blob, blob2)

    def roundtrip_tree(self, entries, expected_hash=None):
        h = self.store.put_tree(entries)
        if expected_hash:
            self.assertEqual(h, expected_hash)
        entries2 = self.store.get_tree(h)
        self.assertEqual(entries, entries2)

    def test_putempty(self):
        self.roundtrip_blob("", hash_empty_blob)
        self.roundtrip_tree([], hash_empty_tree)

        self.roundtrip_blob("foo")
        self.roundtrip_tree([(hashes.mode_blob, "empty", hash_empty_blob)])

    def test_checktree(self):
        hfoo = self.store.put_blob("foo")
        hbar = self.store.put_blob("bar")
        hmissing_blob = hashes.hash_object("missing")
        hmissing_tree = hashes.hash_tree(
            [(hashes.mode_blob, "missing.txt", hmissing_blob)]
        )
        htree = self.store.put_tree(
            [
                (hashes.mode_blob, "foo.txt", hfoo),
                (hashes.mode_blob, "bar.txt", hbar),
                (hashes.mode_tree, "subdir1", hmissing_tree),
                (hashes.mode_tree, "subdir2", hmissing_tree),
            ]
        )
        self.assertEqual(self.store.check_tree(hmissing_tree), [hmissing_tree])
        self.assertEqual(self.store.check_tree(htree), [hmissing_tree])
        self.store.put_tree([(hashes.mode_blob, "missing.txt", hmissing_blob)])
        self.assertEqual(self.store.check_tree(htree), [hmissing_blob])
        self.store.put_blob("missing")
        self.assertEqual(self.store.check_tree(htree), [])


class TestFsStore(unittest.TestCase, BaseTestStore):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = fs_store.FsStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)


class TestMockStore(unittest.TestCase, BaseTestStore):
    def setUp(self):
        self.store = mock_store.MockStore()


if __name__ == "__main__":
    unittest.main()
