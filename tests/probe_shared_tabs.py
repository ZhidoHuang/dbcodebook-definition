"""Offline probe: two independent CLI processes, one context, distinct pages."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from skill_config import load_config, playwright_command
from playwright_session_action import bind_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=True)
    command = playwright_command(load_config(args.config)) + ["-s=tabs-" + uuid.uuid4().hex[:12]]

    def call(*parts):
        return subprocess.run(command + list(parts), cwd=root, capture_output=True,
                              encoding="utf-8", timeout=60)

    result = {}
    jobs = []
    try:
        opened = call("open", "about:blank", "--browser", "msedge", "--headed", "--profile", str(root / "profile"))
        if opened.returncode:
            raise RuntimeError(opened.stdout + opened.stderr)
        setup = root / "setup.js"
        setup.write_text("""async page => {
          const targets={};
          for (const key of ['A','B']) {
            const p=await page.context().newPage();
            await p.goto('about:blank');
            await p.setContent('<input id="text"><input type="file" id="file"><a id="download">Download</a>');
            const cdp=await page.context().newCDPSession(p);
            try {targets[key]=(await cdp.send('Target.getTargetInfo')).targetInfo.targetId;}
            finally {await cdp.detach();}
          }
          return {ok:true,targets};
        }""", encoding="utf-8")
        ready = call("--raw", "run-code", "--filename", str(setup))
        if ready.returncode:
            raise RuntimeError(ready.stdout + ready.stderr)
        targets = json.loads(ready.stdout)["targets"]
        for key in ("A", "B"):
            upload = root / (key + ".txt")
            upload.write_text(key * 100, encoding="utf-8")
            script = root / (key + ".js")
            script.write_text(bind_code("async page => {\nconst key=" + json.dumps(key) + ";\n"
                "const p=page;\n"
                "const start=Date.now();\n"
                "await p.locator('#text').fill(key);\n"
                "await p.locator('#file').setInputFiles(" + json.dumps(str(upload)) + ");\n"
                "await p.waitForTimeout(3000);\n"
                "await p.evaluate(key=>{const a=document.querySelector('#download');"
                "a.href=URL.createObjectURL(new Blob([key.repeat(100)]));a.download=key+'.txt';},key);\n"
                "const pending=p.waitForEvent('download');await p.locator('#download').click();\n"
                "await (await pending).saveAs(" + json.dumps(str(root / (key + "-download.txt"))) + ");\n"
                "return {key,start,end:Date.now(),text:await p.locator('#text').inputValue(),"
                "file:await p.locator('#file').evaluate(el=>el.files[0].name)};}", targets[key]), encoding="utf-8")
            jobs.append(subprocess.Popen(command + ["--raw", "run-code", "--filename", str(script)],
                                         cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         encoding="utf-8"))
        outputs = []
        for job in jobs:
            stdout, stderr = job.communicate(timeout=60)
            outputs.append({"code": job.returncode, "stdout": stdout, "stderr": stderr})
        result["processes"] = outputs
        values = [json.loads(o["stdout"]) for o in outputs if o["code"] == 0]
        result["overlap_ms"] = min(v["end"] for v in values) - max(v["start"] for v in values) if len(values) == 2 else None
        result["isolated"] = len(values) == 2 and all(v["text"] == v["key"] and v["file"] == v["key"] + ".txt" and (root / (v["key"] + "-download.txt")).read_text() == v["key"] * 100 for v in values)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        for job in jobs:
            if job.poll() is None:
                job.kill()
                job.communicate()
        result["close_code"] = call("close").returncode
        (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    main()
