import argparse
import copy
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

installed=Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(installed))
target=Path(sys.argv[1]) if len(sys.argv)>1 else installed/'execution_report.py'
spec=importlib.util.spec_from_file_location('report_under_test',target)
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
start=report.parse_time('2026-10-27T02:00:00+08:00');end=report.parse_time('2026-10-27T03:00:00+08:00')
old={'turn_id':'old','started_at':'2026-10-25T07:00:00+08:00','finished_at':'2026-10-25T07:10:00+08:00','outcome':'completed','elapsed_seconds':600}
active={'turn_id':'other_active','started_at':'2026-10-27T02:50:00+08:00','finished_at':None,'outcome':None,'elapsed_seconds':None}
def rejects(fn,part):
    try:fn()
    except (ValueError,SystemExit) as e:assert part in str(e),(part,str(e))
    else:raise AssertionError('accepted invalid inheritance')

rounds,meta=report.completed_exploration_inheritance([old,active],['old'],'独立探索 A',start,end,'相同来源及范围；沿用原始证据')
assert rounds==[old] and rounds[0]['started_at']=='2026-10-25T07:00:00+08:00'
assert meta['other_unfinished_turn_ids']==['other_active']
assert meta['included_in_current_run_timing'] is False
rejects(lambda:report.completed_exploration_inheritance([old],None,'独立探索 A',start,end,'reason'),'turn-id')
rejects(lambda:report.completed_exploration_inheritance([old],['old'],'独立探索 A',start,end,''),'inherit-reason')
rejects(lambda:report.completed_exploration_inheritance([old],['missing'],'独立探索 A',start,end,'reason'),'真实日志')
rejects(lambda:report.completed_exploration_inheritance([old],['old'],'公开 R 复核',start,end,'reason'),'仅用于独立探索')
rejects(lambda:report.completed_exploration_inheritance([active],['other_active'],'独立探索 A',start,end,'reason'),'普通导入')
unfinished={**old,'finished_at':None,'outcome':None}
rejects(lambda:report.completed_exploration_inheritance([unfinished],['old'],'独立探索 B',start,end,'reason'),'已经完成')
aborted={**old,'outcome':'aborted'}
rejects(lambda:report.completed_exploration_inheritance([aborted],['old'],'独立探索 B',start,end,'reason'),'已经完成')

fake_report={'status':'running','started_at':'2026-10-27T02:00:00+08:00','reviews':[]}
fake_review={'agent_id':'independent','nickname':'Reviewer','created_at':'2026-10-25T06:00:00+08:00','role':'独立探索 A','rounds':[old,active]}
args=argparse.Namespace(process_dir='unused',log=Path('fixture'),role='独立探索 A',turn_id=['old'],inherit_completed=True,inherit_reason='相同完整问卷范围，原成果不变',closed=False,close_unavailable='宿主只有中断工具，无关闭工具；指定轮次已完成')
saved=[]
with patch.object(report,'load',return_value=copy.deepcopy(fake_report)),patch.object(report,'read_review_log',return_value=copy.deepcopy(fake_review)),patch.object(report,'now',return_value=end),patch.object(report,'save',side_effect=lambda *a:saved.append(copy.deepcopy(a[2]))):
    receipt=report.command_review_import(args)
assert receipt['running_seconds']==600
review=saved[0]['reviews'][0]
assert review['timing_scope']['started_at']==old['started_at']
assert review['timing_scope']['through']==old['finished_at']
assert review['timing_scope']['included_in_current_run_timing'] is False
assert review['completed_exploration_inheritance']['other_unfinished_turn_ids']==['other_active']
assert report.review_lifecycle_complete(review)
assert review['closed'] is False
stage={'status':'pass','evidence':'已比较真实原始探索产出','inputs':{'scope':'hash'},'started_at':'2026-10-27T02:10:00+08:00','mode':'independent','agent_id':'independent'}
bound={'reviews':[review],'stage_reviews':{'独立探索 A':stage}}
with patch.object(report,'input_hashes',return_value={'scope':'hash'}):
    assert report.validate_stage_review(bound,'独立探索 A')['agent_id']=='independent'
    without_inheritance=copy.deepcopy(bound)
    without_inheritance['reviews'][0].pop('completed_exploration_inheritance')
    rejects(lambda:report.validate_stage_review(without_inheritance,'独立探索 A'),'实际完成')
    r_bound={'reviews':[{**review,'role':'公开 R 复核'}],'stage_reviews':{'公开 R 复核':stage}}
    rejects(lambda:report.validate_stage_review(r_bound,'公开 R 复核'),'实际完成')

args.inherit_completed=False;args.inherit_reason=None
with patch.object(report,'load',return_value=copy.deepcopy(fake_report)),patch.object(report,'read_review_log',return_value=copy.deepcopy(fake_review)),patch.object(report,'now',return_value=end):
    rejects(lambda:report.command_review_import(args),'本次报告时间范围')
print('COMPLETED_EXPLORATION_INHERITANCE_PASS')
