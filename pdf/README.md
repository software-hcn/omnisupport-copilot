# pdf/

极客时间《AI 数据工程实战营》的讲义与学习笔记。课程代码在仓库其余目录，不在这里。

```
pdf/
  doc/        课程原讲义 PDF（只读，不要改）
  analysis/   去水学习笔记（日常读这里）
  tools/      从 PDF 抽文本的脚本（对照原文时才用）
```

| 目录 | 读谁 | 不要拿它当 |
|---|---|---|
| `doc/` | 需要翻某页原幻灯片时 | 学习主路径（啰嗦） |
| `analysis/` | 每周学习和代码导读 | — |
| `tools/` | 重新从 PDF 抽文本、写新一周笔记时 | 课程运行时的一部分 |

入口：

- [analysis/00-课程学习地图.md](analysis/00-课程学习地图.md)
- [analysis/00-仓库代码导读.md](analysis/00-仓库代码导读.md)

需要对照讲义原文时，在仓库根目录执行：

```bash
python pdf/tools/extract_text.py
```

输出写到 `pdf/_extracted/`（已 gitignore，不提交）。抽完对照 `analysis/` 即可，不必长期保留。
