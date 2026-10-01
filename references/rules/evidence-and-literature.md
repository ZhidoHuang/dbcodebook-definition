# Evidence And Literature

Use evidence to decide the definition before formal R, not to decorate a completed result.

## 按问题决定是否探索文献

模块探索只需查明数据库提供什么，使用目录、问卷、codebook和官方说明，不强制研究文献。具体定义涉及重新归类、阈值、分段或指标构造时，两路各自查适用的分类标准、方法文献及其人群/时期条件；官方已有明确派生方法且不需另作选择时不额外凑文献。

先找适用依据；未找到时说明实际查找范围，再结合题义、数据结构和常理提出本次处理及理由，不冒充文献结论。常理不足以支持的具体诊断阈值或量表切点不得编造，提出保留原值等可行替代或请用户决定。两边相同的推测不是外部证据。

## Evidence Order

1. Actual dbCodeBook variable details, raw codebook, and observed values.
2. Repository official questionnaires, user guides, release notes, and technical documents.
3. Harmonized technical codebooks or traceable construction documentation.
4. Original scale papers, authoritative guidelines, or primary methodological sources.
5. Direct studies that report the relevant items, periods, formulas, and missing handling.
6. Official web material when the repository library lacks the item, a version needs confirmation, or readers need a public link.

For technical questions, prefer primary or official sources. Record what each source explicitly supports, what it does not support, and how it changes the current decision.

For long PDFs, first locate matching pages or sections, then read those passages with their question options and adjacent routing instructions. Save extracted text in the process directory for reuse; do not repeatedly print every keyword match from the entire document. Use an available PDF parser or the host's bundled document runtime rather than assuming a particular executable is on PATH.

## Questionnaire Evidence

For each period and source group represented as original-question content, record:

- official question id and full question text;
- complete options for closed questions;
- population and reference period;
- actual skip conditions and destinations;
- repository material path and page, question, or section locator;
- the copy section that uses the evidence.

Build this record by walking through the original question and every option, including conditions, explicit continuation and exit destinations. Check from original material to record, not just from recorded items back to the original: the latter cannot reveal an omitted route. Put actual omissions or uncertainty in the existing `logic_issues`; do not mark the source plan resolved while an applicable original route is missing. `options_complete` and similar flags describe this work, but are not evidence that it happened.

`local_material_path` is relative to the selected database's material root, not the repository. For CHARLS, the root is `references/source-materials/charls`; write `官方问卷/2011/2011 家户问卷.pdf`, not `references/source-materials/charls/官方问卷/2011/2011 家户问卷.pdf`. The example illustrates the base only; verify the actual filename before using it. For missing materials, record the existing directory actually searched; put page/question details in `locator`, not in the file path.

An explanatory phrase such as “进入工作分支” may clarify a destination but cannot replace an available question number or original destination. Do not present a paraphrase as an original question.

When repository material is absent, record the searched local location and the absence before adding an official web source. A similar website label is not questionnaire evidence.

## Method Decisions

Use literature and Harmonized documentation to check completeness, formulas, thresholds, scoring, missing handling, and cross-period comparability. Distinguish source statements, facts directly verified from questionnaire/raw, and the project's proposed definition.

Formal raw must still come from the current dbCodeBook download. Literature, official questionnaires, Harmonized data, and other datasets cannot substitute for downloaded raw fields.

Keep only references that materially support a definition choice or interpretation. Do not repeat official-questionnaire citations mechanically when the period-design section already presents and locates those questions.
