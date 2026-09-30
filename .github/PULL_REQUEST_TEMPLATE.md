## 这个改动解决了什么

<!-- 一句话说清问题与影响；关联的 issue 用 #编号 -->

## 改了什么

<!-- 列文件或目录，别贴大段 diff -->

## 验证（必填）

- [ ] `py -3 tools/build_codex_surface.py --check`
- [ ] `py -3 tools/validate_plugin.py .`
- [ ] `py -3 -m pytest tests -q`

<!-- 涉及判据、门控、许可、依赖的改动，请附"命令 + 原始输出"或提交 SHA，不要只写"测过了" -->

## 提交前自查

- [ ] 规则只写了一份（结论在 `governance/`，流程在 `commands/`，组件认知在 `governance/oss-components.json`）
- [ ] 没改生成物（`skills/` 由 `commands/` 生成）
- [ ] 没有在仓库里写入真实平台名、内网地址或凭据
- [ ] 文档里的数字与承诺要么有机器校验，要么标注"未验证"
- [ ] 提交带 DCO 签名（`git commit -s`）
