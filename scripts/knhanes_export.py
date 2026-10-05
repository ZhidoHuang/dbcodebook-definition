"""KNHANES website-export contract. Validates a staged bundle, never downloads it.
Synthetic passes are not evidence of a real website export or release acceptance.
"""
from __future__ import annotations
import csv
import re
from pathlib import Path

YEARS = ('1998','2001','2005', *map(str, range(2007,2025)))
REPEATED = frozenset({'Dietary recall detail','Dietary recall second day','Dietary supplement detail','Physical activity monitor'})
# Observed unique-ID file families in this task's own UI receipts s006/s008/s010/s013/s015.
# This is an explicit bounded support set, not an assertion that every other file is unique.
UNIQUE_FILES = frozenset({'Core data','Injury and medical utilization','Disease detail',
    'Oral examination','Eye examination','Bone density examination','Food frequency questionnaire',
    'Ear nose and throat examination','Cycle 7 oral special release','Indoor air quality special release'})
IDENTIFIERS = ('ID','id','year')
RESERVED = frozenset((*IDENTIFIERS,'RowIndex'))
CODEBOOK_COLUMNS = ('Variable','Label原文','Label中文','File type','newname')

def _csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader=csv.DictReader(f)
        fields=reader.fieldnames
        if not fields or len(fields)!=len(set(fields)):
            raise ValueError(f'{path.name}: missing or duplicate header')
        rows=list(reader)
    if any(None in x or any(v is None for v in x.values()) for x in rows):
        raise ValueError(f'{path.name}: ragged CSV row')
    return fields,rows

def _identity(value):
    m=re.fullmatch(r'([^()\s]+)\s+\((.+)\)', value)
    if not m or not m[2].strip():
        raise ValueError('KNHANES dictionary requires full Variable (File): '+value)
    if m[1].lower() in {'id','year'}:
        raise ValueError('KNHANES id/year are automatic identifiers, not selectable sources')
    return m[1], m[2].strip()

def validate_bundle(out_dir: Path, data_members, expected_vars, expected_sources=None):
    out_dir=Path(out_dir)
    expected=list(expected_vars)
    if not expected or any(not isinstance(x,str) or not x.strip() for x in expected) or len(expected)!=len(set(expected)) or any(x in RESERVED for x in expected):
        raise ValueError('KNHANES aliases must be nonempty, unique and not reserved')
    header,codebook=_csv(out_dir/'raw_codebook.csv')
    if not set(CODEBOOK_COLUMNS).issubset(header):
        raise ValueError('KNHANES dictionary missing website columns')
    if len(codebook)!=len(expected) or {x['newname'] for x in codebook}!=set(expected):
        raise ValueError('KNHANES dictionary aliases differ from selection')
    wanted={}
    identities=set()
    for item in codebook:
        alias=item['newname'];variable,file=_identity(item['Variable'])
        identity=(variable,file)
        if identity in identities:
            raise ValueError('KNHANES duplicate source identity')
        identities.add(identity)
        if file not in REPEATED and file not in UNIQUE_FILES:
            raise ValueError('KNHANES unknown source file; explicit type evidence required: '+file)
        kind='reID' if file in REPEATED else 'uniqID'
        if item['File type']!=kind:
            raise ValueError('KNHANES File type contradicts source file')
        member='raw_data_'+file.replace(' ','_')+'.csv' if kind=='reID' else 'raw_data.csv'
        wanted.setdefault(member,[]).append(alias)
        if expected_sources is not None and expected_sources.get(alias)!=item['Variable']:
            raise ValueError('KNHANES original source identity differs from settled selection')
    members=list(data_members)
    if len(members)!=len(set(members)) or set(members)!=set(wanted):
        raise ValueError('KNHANES data file set differs from dictionary source families')
    reports={}
    for member in members:
        if Path(member).name!=member:
            raise ValueError('KNHANES member must be a basename')
        cols,records=_csv(out_dir/member)
        repeated=member!='raw_data.csv'
        prefix=['RowIndex',*IDENTIFIERS] if repeated else list(IDENTIFIERS)
        if cols[:len(prefix)]!=prefix or set(cols[len(prefix):])!=set(wanted[member]):
            raise ValueError(member+': identity prefix or alias coverage differs from dictionary')
        keys=set();rowkeys=set()
        for n,record in enumerate(records,1):
            respondent=record['id'].strip();year=record['year'].strip()
            if not respondent or year not in YEARS:
                raise ValueError(member+': empty id or unsupported year')
            derived=year+'_'+respondent
            if record['ID']!=derived:
                raise ValueError(member+': ID is not year_id')
            key=(respondent,year)
            if not repeated and key in keys:
                raise ValueError(member+': duplicate id-year in unique-ID file')
            keys.add(key)
            if repeated:
                if record['RowIndex']!=str(n):
                    raise ValueError(member+': RowIndex must be website row sequence 1..n')
                rowkey=(record['RowIndex'],record['ID'])
                if rowkey in rowkeys:raise ValueError(member+': duplicate repeated row key')
                rowkeys.add(rowkey)
        reports[member]={'header':cols,'rows':len(records),'cols':len(cols),'identity_columns':prefix,
                         'data_vars':cols[len(prefix):],'unit':'repeated record' if repeated else 'respondent-year',
                         'unique_respondent_years':len(keys)}
    return {'codebook':{'rows':len(codebook),'aliases':[x['newname'] for x in codebook]},'data':reports,
            'verification_scope':'staged CSV contract only; origin and fresh-download provenance checked by caller'}

def validate_person_frame(path: Path):
    """For generation/output checks: regular person-year file, with no repeat collapse."""
    cols,records=_csv(Path(path))
    if cols[:3]!=list(IDENTIFIERS):raise ValueError('KNHANES requires ID,id,year prefix')
    seen=set()
    for record in records:
        key=(record['id'].strip(),record['year'].strip())
        if not key[0] or key[1] not in YEARS or record['ID']!='_'.join((key[1],key[0])):
            raise ValueError('KNHANES invalid string identity or unsupported year')
        if key in seen:raise ValueError('KNHANES duplicate respondent-year')
        seen.add(key)
    return {'rows':len(records),'identity_columns':list(IDENTIFIERS),'unit':'respondent-year'}
