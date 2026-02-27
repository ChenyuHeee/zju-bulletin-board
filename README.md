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

## WebVPN 配置（获取计算机学院真实通知）

计算机学院的通知公告页 (`cspo.zju.edu.cn`) 仅校内可访问。配置 ZJU 账号后，GitHub Actions 将通过 WebVPN 抓取真实通知；未配置则降级为公开新闻页并在页面上显示提示。

### 设置步骤

1. 打开 GitHub 仓库 → **Settings → Secrets and variables → Actions**
2. 点击 **New repository secret**，添加两个 Secret：

| Name | Value |
|------|-------|
| `ZJU_USERNAME` | 浙大统一认证账号（学号/工号） |
| `ZJU_PASSWORD` | 密码 |

配置完成后手动触发一次 Actions（`workflow_dispatch`）即可验证。

> **安全说明**：Secrets 仅在 Actions 运行时注入，不会出现在日志或代码中。仓库若为 Public，外部贡献者的 PR 触发的 Actions **不会**读取到这些 Secrets（GitHub 的默认保护机制）。

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 不使用 WebVPN（公网模式）
python scraper/scrape.py

# 使用 WebVPN（需浙大账号）
ZJU_USERNAME=你的学号 ZJU_PASSWORD=你的密码 python scraper/scrape.py
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
│   └── scrape.py                  # 爬虫主程序（含 WebVPN 登录逻辑）
├── docs/
│   ├── index.html                 # GitHub Pages 展示页
│   └── data.json                  # 爬虫输出（自动更新）
├── requirements.txt
└── README.md
```
