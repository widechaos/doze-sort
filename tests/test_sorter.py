import copy
import json
import tempfile
import unittest
from pathlib import Path
from sorter import Planner,apply,undo,digest
ROOT=Path(__file__).parents[1]
class SorterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner=Planner();cls.topics=json.loads((ROOT/'topics.json').read_text());(ROOT/'.runtime').mkdir(exist_ok=True)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.runtime');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=self.root/'inbox';self.source.mkdir();self.output=self.root/'sorted'
        (self.source/'a.md').write_text('Mix flour and yeast into bread dough. Bake the loaf in a hot oven until the crust is crisp.')
        (self.source/'b.md').write_bytes((self.source/'a.md').read_bytes())
    def plan(self):return self.planner.plan(self.source,self.output,self.topics)
    def snapshot(self):return {p.name:digest(p.read_bytes()) for p in self.source.iterdir() if p.is_file()}
    def test_apply_deduplicates_copies_without_touching_sources(self):
        before=self.snapshot();plan=self.plan();r=apply(plan);self.assertEqual(r['copied'],1);self.assertEqual(r['duplicates'],1);self.assertEqual(before,self.snapshot());run=Path(r['run']);self.assertEqual((run/'cooking/a.md').read_bytes(),(self.source/'a.md').read_bytes())
    def test_undo_moves_run_to_recovery_without_deletion_and_is_idempotent(self):
        p=self.plan();r=apply(p);original=self.snapshot();result=undo(self.output,p['id']);self.assertFalse(Path(r['run']).exists());self.assertTrue(Path(result['recovery']).is_dir());self.assertEqual(result['deleted_files'],0);self.assertEqual(original,self.snapshot());self.assertEqual(undo(self.output,p['id'])['state'],'already undone')
    def test_reapplying_same_plan_never_overwrites(self):
        p=self.plan();apply(p)
        with self.assertRaises(ValueError):apply(p)
        undo(self.output,p['id'])
        with self.assertRaises(ValueError):apply(p)
    def test_changed_or_added_input_invalidates_plan_before_copy(self):
        p=self.plan();(self.source/'a.md').write_text('changed')
        with self.assertRaises(ValueError):apply(p)
        self.assertFalse(self.output.exists())
        p=self.plan();(self.source/'new.md').write_text('A new note after planning.')
        with self.assertRaises(ValueError):apply(p)
    def test_edited_or_extra_output_stops_undo(self):
        p=self.plan();r=apply(p);run=Path(r['run']);(run/'cooking/a.md').write_text('my later edit')
        with self.assertRaises(ValueError):undo(self.output,p['id'])
        self.assertTrue(run.exists())
        (run/'cooking/a.md').write_bytes((self.source/'a.md').read_bytes());(run/'new.txt').write_text('unrelated later file')
        with self.assertRaises(ValueError):undo(self.output,p['id'])
        self.assertTrue((run/'new.txt').exists())
    def test_paths_links_and_nesting_rejected(self):
        p=self.plan();bad=copy.deepcopy(p);bad['files'][0]['name']='../outside.md'
        with self.assertRaises(ValueError):apply(bad)
        (self.source/'linked.md').symlink_to(self.source/'a.md')
        with self.assertRaises(ValueError):self.plan()
        with self.assertRaises(ValueError):self.planner.plan(self.source,self.source/'out',self.topics)
    def test_uncertainty_and_token_limit(self):
        (self.source/'a.md').write_text('ZXQ 7429 LMP. No useful subject appears in this invented sentence.');(self.source/'b.md').unlink()
        p=self.plan();self.assertEqual(p['files'][0]['topic'],'_review')
        (self.source/'a.md').write_text('bread '*400)
        with self.assertRaises(ValueError):self.plan()

if __name__=='__main__':unittest.main()
