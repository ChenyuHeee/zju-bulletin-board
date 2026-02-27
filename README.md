# 浙江大学学院通知公告聚合

每日自动抓取浙江大学三个学院官网的最新通知，发布到 GitHub Pages。

## 包含学院

| 学院 | 通知来源 |
|------|---------|
| 外国语学院 | http://www.sis.zju.edu.cn/sischinese/12577/list.htm |
| 计算机科学与技术学院 | http://cspo.zju.edu.cn/86671/list.htm |
| 竺可桢学院 | http://ckc.zju.edu.cn/54005/list.htm |

## 工作原理

```
GitHub Actions Schedule (每天 08:00 北京时间)
       │
       ▼
scraper/scrape.py  ← 抓取各学院列表页前 2 页
       │
       ▼  写入
docs/data.json     ← 自动 commit & push
       │
       ▼  部署
GitHub Pages (docs/)  ← 展示通知列表
```

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 执行爬虫（结果写入 docs/data.json）
python scraper/scrape.py
```

## 网站结构说明

三个学院均使用**浙大 WebPlus CMS**，特征：
- 列表 URL 固定：`/{category_id}/list.htm`（分页为 `list2.htm`…）
- 文章 URL 格式：`/{domain}/{YYYY}/{MMDD}/c{category}a{article}/page.htm`
- 每页约 14–15 条，爬虫默认抓取前 2 页（最新 ~30 条/学院）

如学院更换域名或栏目 ID，只需修改 `scraper/scrape.py` 顶部的 `COLLEGES` 配置。

## 目录结构

```
.
├── .github/workflows/scrape.yml   # GitHub Actions：每日抓取 + 部署
├── scraper/
│   └── scrape.py                  # 爬虫主程序
├── docs/
│   ├── index.html                 # GitHub Pages 展示页
│   └── data.json                  # 爬虫输出（自动更新）
├── requirements.txt
└── README.md
```
