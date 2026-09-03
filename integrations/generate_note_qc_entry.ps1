param(
    [Parameter(Mandatory = $true)][string]$DefinitionRoot,
    [Parameter(Mandatory = $true)][string]$PromoRoot,
    [Parameter(Mandatory = $true)][string]$XiaohongshuRoot,
    [Parameter(Mandatory = $true)][string]$SmallbookRoot
)

$ErrorActionPreference = "Stop"

$formalRoot = Join-Path $DefinitionRoot "CHARLS"
$executionRoot = Join-Path (Join-Path $DefinitionRoot "_执行线程") "CHARLS"
$entryPath = Join-Path $DefinitionRoot "CHARLS_笔记质控入口.html"
$dataPath = Join-Path $DefinitionRoot "CHARLS_笔记质控入口_data.js"

function Get-OneFile {
    param(
        [string]$Directory,
        [string]$Filter
    )

    $files = @(Get-ChildItem -LiteralPath $Directory -File -Filter $Filter)
    if ($files.Count -ne 1) {
        throw "$Directory should contain exactly one $Filter file; found $($files.Count)."
    }
    return $files[0]
}

function Get-RichtextArticleHtml {
    param([string]$Path)

    $source = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    $match = [regex]::Match(
        $source,
        '<article\b[^>]*\bid=["'']article["''][^>]*>([\s\S]*?)</article>',
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    if (-not $match.Success) {
        throw "$Path does not contain article#article."
    }
    return $match.Groups[1].Value
}

function HtmlEncode {
    param([string]$Value)
    return [System.Net.WebUtility]::HtmlEncode($Value)
}

function RelativeWebPath {
    param(
        [string]$FromDirectory,
        [string]$Target
    )

    $fromUri = [Uri]::new(($FromDirectory.TrimEnd("\") + "\"))
    $targetUri = [Uri]::new($Target)
    return [Uri]::UnescapeDataString($fromUri.MakeRelativeUri($targetUri).ToString())
}

function Get-EvidenceFile {
    param(
        [string]$ExecutionDirectory
    )

    if (-not (Test-Path -LiteralPath $ExecutionDirectory)) {
        return $null
    }

    $files = @(
        Get-ChildItem -LiteralPath $ExecutionDirectory -Recurse -File -Filter "*.md" |
            Where-Object {
                $_.Name -match "evidence|candidate|literature|research|adjudication|证据|文献"
            }
    )
    if ($files.Count -eq 0) {
        return $null
    }

    return $files |
        Sort-Object -Property @{
            Expression = {
                if ($_.Name -match "^evidence_\d+\.md$") { 0 }
                elseif ($_.Name -match "证据包") { 1 }
                elseif ($_.Name -eq "candidate_package.md") { 2 }
                elseif ($_.Name -match "literature_and_candidate") { 3 }
                elseif ($_.Name -match "research_adjudication") { 4 }
                else { 5 }
            }
        }, FullName |
        Select-Object -First 1
}

$displayOverrides = @{
    "003" = "身体活动"
    "012" = "CES-D"
}

$topics = @(
    Get-ChildItem -LiteralPath $formalRoot -Directory |
        Where-Object { $_.Name -match "^(\d{3})_(.+)$" } |
        Sort-Object Name |
        ForEach-Object {
            $id = [regex]::Match($_.Name, "^(\d{3})_").Groups[1].Value
            $folderTitle = $_.Name.Substring(4)
            $title = if ($displayOverrides.ContainsKey($id)) {
                $displayOverrides[$id]
            } else {
                $folderTitle
            }

            [pscustomobject]@{
                Id = $id
                Title = $title
                Directory = $_
                Note = Get-OneFile -Directory $_.FullName -Filter "*_笔记.md"
                Definition = Get-OneFile -Directory $_.FullName -Filter "*_definition.html"
                Detail = Get-OneFile -Directory $_.FullName -Filter "*_detail.html"
                QA = Get-OneFile -Directory $_.FullName -Filter "CHARLS_*_QA.txt"
                Log = Get-OneFile -Directory $_.FullName -Filter "*.log"
                PromoDirectory = Join-Path $PromoRoot $_.Name
                Cover = Join-Path (Join-Path $PromoRoot $_.Name) "笔记封面图_右侧内框_800x450.png"
                Evidence = Get-EvidenceFile -ExecutionDirectory (Join-Path $executionRoot $_.Name)
            }
        }
)

if ($topics.Count -eq 0) {
    throw "No complete CHARLS definition topics found."
}

$cards = foreach ($topic in $topics) {
    $id = HtmlEncode $topic.Id
    $title = HtmlEncode $topic.Title
    $topicDirectory = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Directory.FullName
    $notePath = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Note.FullName
    $definitionPath = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Definition.FullName
    $detailPath = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Detail.FullName
    $qaPath = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.QA.FullName
    $evidenceMarkup = ""
    if ($null -ne $topic.Evidence) {
        $evidencePath = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Evidence.FullName
        $evidenceMarkup = @"
            <span class="split-action">
              <a href="$(HtmlEncode $evidencePath)">证据卡</a>
              <button type="button" data-copy-key="$id`:evidence" aria-label="复制证据卡" title="复制证据卡"><span aria-hidden="true">⧉</span></button>
            </span>
"@
    }

    if (Test-Path -LiteralPath $topic.Cover) {
        $coverPath = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Cover
        $coverMarkup = "<img class=""cover"" src=""$(HtmlEncode $coverPath)"" alt=""$id $title 笔记封面"">"
    } else {
        $coverMarkup = @"
        <div class="cover placeholder" aria-label="$id $title 暂无笔记封面">
          <span>CHARLS</span>
          <strong>$id</strong>
        </div>
"@
    }

    @"
      <article>
        $coverMarkup
        <div class="body">
          <div class="meta">
            <span class="number">$id</span>
            <span class="status">MACHINE_CHECK_PASS</span>
          </div>
          <h2>$title</h2>
          <div class="actions">
            <span class="split-action">
              <a href="$(HtmlEncode $notePath)">笔记</a>
              <button type="button" data-copy-key="$id`:note" aria-label="复制笔记" title="复制笔记"><span aria-hidden="true">⧉</span></button>
            </span>
            <span class="split-action">
              <a href="$(HtmlEncode $definitionPath)">定义卡</a>
              <button type="button" data-copy-key="$id`:definition" aria-label="复制定义卡" title="复制定义卡"><span aria-hidden="true">⧉</span></button>
            </span>
            <span class="split-action">
              <a href="$(HtmlEncode $detailPath)">详情</a>
              <button type="button" data-copy-key="$id`:detail" aria-label="复制详情" title="复制详情"><span aria-hidden="true">⧉</span></button>
            </span>
            $evidenceMarkup
            <span class="split-action">
              <a href="$(HtmlEncode $qaPath)">QA</a>
              <button type="button" data-copy-key="$id`:qa" aria-label="复制 QA" title="复制 QA"><span aria-hidden="true">⧉</span></button>
            </span>
            <a class="secondary" href="$(HtmlEncode $topicDirectory)">打开目录</a>
          </div>
        </div>
      </article>
"@
}

$firstId = $topics[0].Id
$lastId = $topics[-1].Id
$topicCount = $topics.Count

$wechatTopics = @(
    $topics | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.PromoDirectory "公众号富文本.html")) -and
        (Test-Path -LiteralPath (Join-Path $_.PromoDirectory "公众号封面_preview.png"))
    }
)

$wechatCards = foreach ($topic in $wechatTopics) {
    $id = HtmlEncode $topic.Id
    $title = HtmlEncode $topic.Title
    $cover = RelativeWebPath -FromDirectory $DefinitionRoot -Target (Join-Path $topic.PromoDirectory "公众号封面_preview.png")
    $richtext = RelativeWebPath -FromDirectory $DefinitionRoot -Target (Join-Path $topic.PromoDirectory "公众号富文本.html")
    $coverPreview = RelativeWebPath -FromDirectory $DefinitionRoot -Target (Join-Path $topic.PromoDirectory "公众号封面_preview.png")

    @"
      <article>
        <img class="cover wechat-cover" src="$(HtmlEncode $cover)" alt="$id $title 公众号封面">
        <div class="body">
          <div class="meta">
            <span class="number">$id</span>
            <span class="status">公众号材料齐全</span>
          </div>
          <h2>$title</h2>
          <div class="actions">
            <span class="split-action">
              <a href="$(HtmlEncode $richtext)">富文本</a>
              <button type="button" data-copy-rich-key="$id`:richtext" aria-label="复制富文本正文" title="复制富文本正文"><span aria-hidden="true">⧉</span></button>
            </span>
            <span class="split-action secondary">
              <a href="$(HtmlEncode $coverPreview)">封面</a>
              <button type="button" data-copy-image-key="$id`:cover" aria-label="复制封面图片" title="复制封面图片"><span aria-hidden="true">⧉</span></button>
            </span>
          </div>
        </div>
      </article>
"@
}

$wechatCount = $wechatTopics.Count

$xiaohongshuTopics = @()
if (Test-Path -LiteralPath $XiaohongshuRoot) {
    $xiaohongshuTopics = @(
        Get-ChildItem -LiteralPath $XiaohongshuRoot -Directory |
            Where-Object { $_.Name -match "^(\d{3})_(.+)$" } |
            Sort-Object Name |
            ForEach-Object {
                $id = [regex]::Match($_.Name, "^(\d{3})_").Groups[1].Value
                $definitionTopic = @($topics | Where-Object { $_.Id -eq $id } | Select-Object -First 1)
                $title = if ($definitionTopic.Count -eq 1) {
                    $definitionTopic[0].Title
                } else {
                    $_.Name.Substring(4)
                }
                $pages = @(Get-ChildItem -LiteralPath $_.FullName -File -Filter "小红书_*.png" | Sort-Object Name)
                $publishingCopy = @(Get-ChildItem -LiteralPath $_.FullName -File -Filter "*发布文案*.txt")
                if ($pages.Count -gt 0 -and $publishingCopy.Count -eq 1) {
                    [pscustomobject]@{
                        Id = $id
                        Title = $title
                        Directory = $_
                        Cover = $pages[0]
                        PageCount = $pages.Count
                        PublishingCopy = $publishingCopy[0]
                    }
                }
            }
    )
}

$xiaohongshuCards = foreach ($topic in $xiaohongshuTopics) {
    $id = HtmlEncode $topic.Id
    $title = HtmlEncode $topic.Title
    $topicDirectory = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Directory.FullName
    $cover = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Cover.FullName
    $publishingCopy = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.PublishingCopy.FullName

    @"
      <article>
        <img class="cover xiaohongshu-cover" src="$(HtmlEncode $cover)" alt="$id $title 小红书封面">
        <div class="body">
          <div class="meta">
            <span class="number">$id</span>
            <span class="status">$($topic.PageCount) 页</span>
          </div>
          <h2>$title</h2>
          <div class="actions">
            <a class="secondary" href="$(HtmlEncode $topicDirectory)">图组</a>
            <span class="split-action">
              <a href="$(HtmlEncode $publishingCopy)">文案</a>
              <button type="button" data-copy-key="$id`:xiaohongshu-copy" aria-label="复制小红书发布文案" title="复制小红书发布文案"><span aria-hidden="true">⧉</span></button>
            </span>
          </div>
        </div>
      </article>
"@
}

$xiaohongshuCount = $xiaohongshuTopics.Count

$smallbookTopics = @()
if (Test-Path -LiteralPath $SmallbookRoot) {
    $smallbookTopics = @(
        Get-ChildItem -LiteralPath $SmallbookRoot -Directory |
            Where-Object { $_.Name -match "^(\d{3})_(.+)$" } |
            Sort-Object Name |
            ForEach-Object {
                $id = [regex]::Match($_.Name, "^(\d{3})_").Groups[1].Value
                $definitionTopic = @($topics | Where-Object { $_.Id -eq $id } | Select-Object -First 1)
                $title = if ($definitionTopic.Count -eq 1) {
                    $definitionTopic[0].Title
                } else {
                    $_.Name.Substring(4)
                }
                $richtext = Join-Path $_.FullName "公众号富文本.html"
                $cover = Join-Path $_.FullName "公众号封面.png"
                if ((Test-Path -LiteralPath $richtext) -and (Test-Path -LiteralPath $cover)) {
                    [pscustomobject]@{
                        Id = $id
                        Title = $title
                        Directory = $_
                        Richtext = $richtext
                        Cover = $cover
                    }
                }
            }
    )
}

$smallbookCards = foreach ($topic in $smallbookTopics) {
    $id = HtmlEncode $topic.Id
    $title = HtmlEncode $topic.Title
    $richtext = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Richtext
    $cover = RelativeWebPath -FromDirectory $DefinitionRoot -Target $topic.Cover

    @"
      <article>
        <img class="cover" src="$(HtmlEncode $cover)" alt="$id $title 小book封面">
        <div class="body">
          <div class="meta">
            <span class="number">$id</span>
            <span class="status">小book材料齐全</span>
          </div>
          <h2>$title</h2>
          <div class="actions">
            <span class="split-action">
              <a href="$(HtmlEncode $richtext)">富文本</a>
              <button type="button" data-copy-rich-key="$id`:smallbook-richtext" aria-label="复制小book富文本正文" title="复制小book富文本正文"><span aria-hidden="true">⧉</span></button>
            </span>
            <span class="split-action secondary">
              <a href="$(HtmlEncode $cover)">封面</a>
              <button type="button" data-copy-image-key="$id`:smallbook-cover" aria-label="复制小book封面图片" title="复制小book封面图片"><span aria-hidden="true">⧉</span></button>
            </span>
          </div>
        </div>
      </article>
"@
}

$smallbookCount = $smallbookTopics.Count

$html = @"
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CHARLS 定义笔记 $firstId-$lastId 质控入口</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #f4f3f0;
      color: #172333;
      font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    }
    main {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 42px 0 64px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 30px;
      letter-spacing: 0;
    }
    .lead {
      margin: 0 0 28px;
      color: #667085;
      font-size: 15px;
      line-height: 1.7;
    }
    .tabs {
      display: flex;
      gap: 8px;
      margin: 0 0 24px;
    }
    .tab-button {
      min-width: 104px;
      color: #667085;
      background: #fffdf9;
      border: 1px solid #e8d7d4;
    }
    .tab-button.is-active {
      color: #fffdf9;
      background: #a33842;
      border-color: #a33842;
    }
    .tab-panel[hidden] { display: none; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 18px;
    }
    article {
      overflow: hidden;
      background: #fffdf9;
      border: 1px solid #e8d7d4;
      border-radius: 8px;
    }
    .cover {
      display: block;
      width: 100%;
      height: auto;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      background: #faf6ef;
    }
    .cover.placeholder {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #a33842;
      background:
        linear-gradient(145deg, #fffdf9 0 48%, #faf6ef 48% 100%);
    }
    .cover.placeholder span {
      font-size: 28px;
      font-weight: 700;
    }
    .cover.placeholder strong {
      position: absolute;
      right: 22px;
      top: 20px;
      font-family: "Cascadia Code", Consolas, monospace;
      font-size: 14px;
    }
    .cover.wechat-cover {
      aspect-ratio: 2700 / 1149;
    }
    .cover.xiaohongshu-cover {
      aspect-ratio: 3 / 4;
      object-position: top center;
    }
    .body { padding: 18px; }
    .meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 0 0 8px;
    }
    .number {
      color: #a33842;
      font-family: "Cascadia Code", Consolas, monospace;
      font-size: 13px;
      font-weight: 700;
    }
    .status {
      color: #667085;
      font-size: 12px;
    }
    h2 {
      margin: 0 0 14px;
      font-size: 20px;
      line-height: 1.5;
      letter-spacing: 0;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .split-action {
      display: inline-flex;
      overflow: hidden;
      background: #f7e7e4;
      border-radius: 6px;
    }
    .split-action > a {
      flex: 0 1 auto;
      min-width: 0;
      padding: 8px 11px;
      border-radius: 0;
      text-align: center;
      white-space: nowrap;
    }
    .split-action > button {
      flex: 0 0 34px;
      width: 34px;
      min-width: 34px;
      padding: 8px 0;
      border-left: 1px solid #e8d7d4;
      border-radius: 0;
      font-family: "Cascadia Code", Consolas, monospace;
      text-align: center;
    }
    a,
    button {
      display: inline-block;
      padding: 8px 12px;
      color: #a33842;
      background: #f7e7e4;
      border: 0;
      border-radius: 6px;
      text-decoration: none;
      font-family: inherit;
      font-size: 14px;
      font-weight: 600;
      line-height: 1.45;
      cursor: pointer;
    }
    a:hover,
    button:hover { background: #f2dcd8; }
    a.secondary {
      color: #475467;
      background: #f4f3f0;
    }
    .split-action.secondary {
      background: #f4f3f0;
    }
    .split-action.secondary > a,
    .split-action.secondary > button {
      color: #475467;
      background: #f4f3f0;
    }
    .split-action.secondary > button {
      border-left-color: #dedbd4;
    }
    .split-action.secondary > a:hover,
    .split-action.secondary > button:hover {
      background: #eae7e0;
    }
    .split-action.secondary > button.is-copied,
    button.is-copied {
      color: #fffdf9;
      background: #a33842;
    }
  </style>
</head>
<body>
  <main>
    <h1>CHARLS 定义笔记 $firstId-$lastId</h1>
    <p class="lead">集中检查定义笔记与各渠道正式材料。</p>
    <nav class="tabs" aria-label="质控入口类型">
      <button type="button" class="tab-button is-active" data-tab-target="notes" aria-selected="true">定义笔记</button>
      <button type="button" class="tab-button" data-tab-target="wechat" aria-selected="false">公众号</button>
      <button type="button" class="tab-button" data-tab-target="xiaohongshu" aria-selected="false">小红书</button>
      <button type="button" class="tab-button" data-tab-target="smallbook" aria-selected="false">小book</button>
    </nav>
    <section class="tab-panel" data-tab-panel="notes">
      <p class="lead">共 $topicCount 个主题。复制正式笔记，并检查定义卡、变量详情、证据卡、QA 与主题交付目录。</p>
      <div class="grid">
$($cards -join "`n")
      </div>
    </section>
    <section class="tab-panel" data-tab-panel="wechat" hidden>
      <p class="lead">共 $wechatCount 个材料齐全的主题。集中检查公众号富文本与封面。</p>
      <div class="grid">
$($wechatCards -join "`n")
      </div>
    </section>
    <section class="tab-panel" data-tab-panel="xiaohongshu" hidden>
      <p class="lead">共 $xiaohongshuCount 个正式主题。集中检查小红书图组与发布文案。</p>
      <div class="grid">
$($xiaohongshuCards -join "`n")
      </div>
    </section>
    <section class="tab-panel" data-tab-panel="smallbook" hidden>
      <p class="lead">共 $smallbookCount 个材料齐全的主题。集中检查小book富文本与封面。</p>
      <div class="grid">
$($smallbookCards -join "`n")
      </div>
    </section>
  </main>
  <script src="CHARLS_笔记质控入口_data.js"></script>
  <script>
    function decodeNote(encoded) {
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      return new TextDecoder("utf-8").decode(bytes);
    }

    function decodeBytes(encoded) {
      return Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
    }

    async function copyText(text) {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
      }
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      if (!copied) throw new Error("copy failed");
    }

    async function copyRichHtml(html) {
      const holder = document.createElement("div");
      holder.innerHTML = html;
      holder.setAttribute("contenteditable", "true");
      holder.style.position = "fixed";
      holder.style.left = "-100000px";
      holder.style.top = "0";
      holder.style.width = "750px";
      document.body.appendChild(holder);

      try {
        if (navigator.clipboard && window.ClipboardItem) {
          await navigator.clipboard.write([
            new ClipboardItem({
              "text/html": new Blob([html], { type: "text/html" }),
              "text/plain": new Blob([holder.innerText], { type: "text/plain" })
            })
          ]);
          return;
        }
        throw new Error("fallback");
      } catch (error) {
        const range = document.createRange();
        const selection = window.getSelection();
        range.selectNodeContents(holder);
        selection.removeAllRanges();
        selection.addRange(range);
        const copied = document.execCommand("copy");
        selection.removeAllRanges();
        if (!copied) throw new Error("copy failed");
      } finally {
        holder.remove();
      }
    }

    async function copyPng(encoded) {
      const blob = new Blob([decodeBytes(encoded)], { type: "image/png" });
      try {
        if (navigator.clipboard && window.ClipboardItem) {
          await navigator.clipboard.write([
            new ClipboardItem({ "image/png": blob })
          ]);
          return;
        }
        throw new Error("fallback");
      } catch (error) {
        const holder = document.createElement("div");
        const image = document.createElement("img");
        holder.setAttribute("contenteditable", "true");
        holder.style.position = "fixed";
        holder.style.left = "-100000px";
        holder.style.top = "0";
        image.src = "data:image/png;base64," + encoded;
        holder.appendChild(image);
        document.body.appendChild(holder);
        try {
          if (image.decode) await image.decode();
          const range = document.createRange();
          const selection = window.getSelection();
          range.selectNode(image);
          selection.removeAllRanges();
          selection.addRange(range);
          const copied = document.execCommand("copy");
          selection.removeAllRanges();
          if (!copied) throw new Error("copy failed");
        } finally {
          holder.remove();
        }
      }
    }

    document.addEventListener("click", async event => {
      const tabButton = event.target.closest("[data-tab-target]");
      if (tabButton) {
        const target = tabButton.dataset.tabTarget;
        document.querySelectorAll("[data-tab-target]").forEach(button => {
          const active = button.dataset.tabTarget === target;
          button.classList.toggle("is-active", active);
          button.setAttribute("aria-selected", active ? "true" : "false");
        });
        document.querySelectorAll("[data-tab-panel]").forEach(panel => {
          panel.hidden = panel.dataset.tabPanel !== target;
        });
        history.replaceState(null, "", "#" + target);
        return;
      }

      const button = event.target.closest("[data-copy-key], [data-copy-rich-key], [data-copy-image-key]");
      if (!button) return;

      let copyAction = null;
      if (button.dataset.copyKey) {
        const encoded = window.__notePayloads && window.__notePayloads[button.dataset.copyKey];
        if (!encoded) return;
        copyAction = () => copyText(decodeNote(encoded));
      } else if (button.dataset.copyRichKey) {
        const encoded = window.__notePayloads && window.__notePayloads[button.dataset.copyRichKey];
        if (!encoded) return;
        copyAction = () => copyRichHtml(decodeNote(encoded));
      } else if (button.dataset.copyImageKey) {
        const encoded = window.__notePayloads && window.__notePayloads[button.dataset.copyImageKey];
        if (!encoded) return;
        copyAction = () => copyPng(encoded);
      }
      if (!copyAction) return;

      const originalContent = button.innerHTML;
      button.disabled = true;
      try {
        await copyAction();
        button.innerHTML = '<span aria-hidden="true">✓</span>';
        button.classList.add("is-copied");
      } catch (error) {
        button.innerHTML = '<span aria-hidden="true">!</span>';
      }
      window.setTimeout(() => {
        button.innerHTML = originalContent;
        button.classList.remove("is-copied");
        button.disabled = false;
      }, 1600);
    });

    const initialTab = location.hash.slice(1);
    const initialButton = document.querySelector('[data-tab-target="' + initialTab + '"]');
    if (initialButton) initialButton.click();
  </script>
</body>
</html>
"@

$payload = [ordered]@{}
foreach ($topic in $topics) {
    $payload["$($topic.Id):note"] = [Convert]::ToBase64String(
        [System.IO.File]::ReadAllBytes($topic.Note.FullName)
    )
    $payload["$($topic.Id):definition"] = [Convert]::ToBase64String(
        [System.IO.File]::ReadAllBytes($topic.Definition.FullName)
    )
    $payload["$($topic.Id):detail"] = [Convert]::ToBase64String(
        [System.IO.File]::ReadAllBytes($topic.Detail.FullName)
    )
    $payload["$($topic.Id):qa"] = [Convert]::ToBase64String(
        [System.IO.File]::ReadAllBytes($topic.QA.FullName)
    )
    if ($null -ne $topic.Evidence) {
        $payload["$($topic.Id):evidence"] = [Convert]::ToBase64String(
            [System.IO.File]::ReadAllBytes($topic.Evidence.FullName)
        )
    }
}
foreach ($topic in $wechatTopics) {
    $richtextPath = Join-Path $topic.PromoDirectory "公众号富文本.html"
    $coverPath = Join-Path $topic.PromoDirectory "公众号封面_preview.png"
    $articleHtml = Get-RichtextArticleHtml -Path $richtextPath
    $payload["$($topic.Id):richtext"] = [Convert]::ToBase64String(
        [System.Text.Encoding]::UTF8.GetBytes($articleHtml)
    )
    $payload["$($topic.Id):cover"] = [Convert]::ToBase64String(
        [System.IO.File]::ReadAllBytes($coverPath)
    )
}
foreach ($topic in $xiaohongshuTopics) {
    $payload["$($topic.Id):xiaohongshu-copy"] = [Convert]::ToBase64String(
        [System.IO.File]::ReadAllBytes($topic.PublishingCopy.FullName)
    )
}
foreach ($topic in $smallbookTopics) {
    $articleHtml = Get-RichtextArticleHtml -Path $topic.Richtext
    $payload["$($topic.Id):smallbook-richtext"] = [Convert]::ToBase64String(
        [System.Text.Encoding]::UTF8.GetBytes($articleHtml)
    )
    $payload["$($topic.Id):smallbook-cover"] = [Convert]::ToBase64String(
        [System.IO.File]::ReadAllBytes($topic.Cover)
    )
}
$data = "window.__notePayloads = $($payload | ConvertTo-Json -Compress);`n"

[System.IO.File]::WriteAllText($entryPath, $html, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($dataPath, $data, [System.Text.UTF8Encoding]::new($false))

[pscustomobject]@{
    Entry = $entryPath
    Data = $dataPath
    FirstId = $firstId
    LastId = $lastId
    Topics = $topicCount
    Covers = @($topics | Where-Object { Test-Path -LiteralPath $_.Cover }).Count
    Placeholders = @($topics | Where-Object { -not (Test-Path -LiteralPath $_.Cover) }).Count
    EvidenceCards = @($topics | Where-Object { $null -ne $_.Evidence }).Count
    WechatTopics = $wechatCount
    XiaohongshuTopics = $xiaohongshuCount
    SmallbookTopics = $smallbookCount
}
