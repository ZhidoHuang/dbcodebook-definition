import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from skill_config import playwright_command
from playwright_session_action import Session
from check_definition_source_record import resolve_material_path
from check_definition_output import charls_identity_data_read, check_public_code_outline


def check_charls_identity_combinations():
    header = ['ID', 'id', 'year', 'householdid', 'communityid', 'value']
    valid = [
        'dt <- read.csv("raw_data.csv")',
        'dt <- read.csv("raw_data.csv", colClasses = c(id = "character", householdid = "character"))',
        "dt<-read.csv('raw_data.csv',colClasses=c(householdid='character',id='character'))",
        '# preceding comment\ndt <- read.csv(\n "raw_data.csv",\n colClasses=c(communityid="character", householdid="character", id="character"))',
    ]
    invalid = [
        '# '+valid[1],
        'text <- '+repr(valid[1]),
        valid[1].replace('householdid = "character"', 'value = "character"'),
        valid[1].replace('householdid = "character"', 'id = "character"'),
        valid[1].replace('id = "character"', 'id = "numeric"'),
        valid[1].replace('raw_data.csv', 'wrong.csv'),
        valid[1][:-1]+', na.strings="0")',
        valid[1][:-1]+', check.names=FALSE)',
        valid[1]+'\n'+valid[0],
    ]
    for code in valid:
        assert charls_identity_data_read(code,'raw_data.csv',header,False), code
    for code in invalid:
        assert not charls_identity_data_read(code,'raw_data.csv',header,False), code
    assert not charls_identity_data_read(valid[1],'raw_data.csv',['ID','id','year'],False)
    family = 'dt <- read.csv("raw_data_household.csv", colClasses=c(year="character",householdid="character",id="character"))'
    assert charls_identity_data_read(family,'raw_data_household.csv',['householdid','year','id'],True)
    assert not charls_identity_data_read(family.replace('year="character",',''),'raw_data_household.csv',['householdid','year','id'],True)
    assert not charls_identity_data_read(family.replace('id="character"','value="character"'),'raw_data_household.csv',['householdid','year','id','value'],True)
    # Exercise the actual outline call, including the separate household read.
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);script=root/'define_charls.R'
        (root/'raw_data.csv').write_text(','.join(header)+'\n',encoding='utf-8')
        for code,accepted in [(valid[1],True),(invalid[2],False),('# '+valid[1],False)]:
            public=code+'\nname_z <- read.csv("raw_codebook.csv")\nhousehold_data <- read.csv("raw_data_household.csv", colClasses=c(householdid="character",respondent_id="character"))\n'
            script.write_text(public+'# 输出\n',encoding='utf-8')
            checks=[]
            check_public_code_outline(root,'### 2-代码材料\n```r\n'+public+'```',checks,'charls',script)
            details=[str(x.get('detail','')) for x in checks if x['check']=='public R structural contract']
            rejected=any('must use the simple read' in d for d in details)
            assert rejected != accepted, (code,details)


check_charls_identity_combinations()

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    cli = root / "portable cli.js"
    cli.touch()
    config = {"executables": {"playwright_cli": str(cli), "node": sys.executable}}
    with patch("skill_config.shutil.which", return_value=None):
        assert playwright_command(config) == [sys.executable, str(cli)]
        session = Session("fixture", root, root / "action.js", config)
        assert session.command == [sys.executable, str(cli), "-s=fixture"]
        try:
            playwright_command({})
        except FileNotFoundError as error:
            assert "playwright_cli" in str(error)
        else:
            raise AssertionError("Missing CLI should not dispatch an action")
    with patch("skill_config.shutil.which", side_effect=lambda x: "npx" if x == "npx" else None):
        assert "--offline" in playwright_command({})
    missing = {"executables": {"playwright_cli": str(root / "missing.js")}}
    try:
        playwright_command(missing)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Configured missing CLI must not silently fall back")
    material = root / "materials"
    material.mkdir()
    assert resolve_material_path("questionnaires/2011.pdf", "CHARLS", material) == material / "questionnaires/2011.pdf"
    for bad in ("references/source-materials/charls/questionnaires/2011.pdf",
                "references\\source-materials\\CHARLS\\questionnaires\\2011.pdf"):
        try:
            resolve_material_path(bad, "CHARLS", material)
        except ValueError as error:
            assert "not the repository" in str(error)
            assert "use 'questionnaires/2011.pdf'" in str(error)
        else:
            raise AssertionError("Wrong material base should have an actionable diagnostic")

    rscript = os.environ.get("RSCRIPT")
    if not rscript:
        raise RuntimeError("RSCRIPT is required for semantic raw-reader tests")
    script = root / "reads.R"
    script.write_text('''
source(Sys.getenv("RAW_READ_HELPER"), encoding="UTF-8")
valid <- c(
  'dt<-read.csv("raw_data.csv")',
  "dt <- read.csv('raw_data.csv', colClasses=c(id='character'))",
  'dt <- read.csv(\n "raw_data.csv",\n colClasses=c(communityid="character", householdid="character", id="character"))'
)
for (x in valid) {
  check_public_raw_reads(c(x, "name_z<-read.csv('raw_codebook.csv')", '# 输出', 'stop("must not execute")'))
}
invalid <- c(
  '# dt <- read.csv("raw_data.csv")',
  'dt <- read.csv("wrong.csv")',
  'dt <- read.csv("raw_data.csv", colClasses=c(value="character"))',
  'dt <- read.csv("raw_data.csv", colClasses=c(id="numeric"))',
  'dt <- read.csv("raw_data.csv", colClasses=c(id="character", id="character"))',
  'dt <- read.csv("raw_data.csv", na.strings="0")',
  'dt <- read.csv("raw_data.csv", colClasses=c(id="character"), check.names=FALSE)'
)
for (x in invalid) {
  failed <- inherits(try(check_public_raw_reads(c(x, 'name_z <- read.csv("raw_codebook.csv")')), silent=TRUE), "try-error")
  stopifnot(failed)
}
cat("SEMANTIC_RAW_READS_PASS\\n")
''', encoding="utf-8")
    env = dict(os.environ, RAW_READ_HELPER=str(ROOT / "scripts/check_public_raw_reads.R"))
    for key in ("LC_ALL", "LC_CTYPE", "LANG"):
        env.pop(key, None)
    result = subprocess.run([rscript, "--vanilla", "--encoding=UTF-8", str(script)],
                            capture_output=True, encoding="utf-8", env=env)
    assert result.returncode == 0, result.stdout + result.stderr

print("EXECUTION_INTERFACES_PASS: direct/offline CLI, material base diagnostics, parsed R reads")
