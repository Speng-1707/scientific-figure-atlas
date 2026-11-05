# 科研图鉴 Figure Atlas

完全由 GitHub 托管的科研图片共享图库：GitHub Pages 提供网页，Issue Form 接收投稿，GitHub Actions 自动分类、提取完整代表色板，并把图片、论文和元数据保存回仓库。

## 投稿

1. 打开网站，点击“分享一张好图”。
2. 登录 GitHub 并填写投稿表。
3. 填写投稿人姓名、机构等信息，将推荐图片拖入“科研图片”输入框，可选拖入论文 PDF。
4. 提交 Issue。工作流处理完成后会回复网站链接并关闭 Issue。

公开仓库中的图片、论文、Issue 和处理结果对所有人可见。请只上传有权公开分享的材料。

## 自动处理流程

```text
GitHub Issue 投稿
  → 校验 GitHub 附件和文件大小
  → 规范化图片并删除 EXIF
  → 关键词分类（或采用投稿者选择）
  → 提取最多 18 个代表色（彩色与有意义的中性色）
  → PDF 中符合尺寸要求的内嵌图片自动抓取、分类并标记来源
  → 保存到 site/assets 和 data/figures.json
  → GitHub Pages 自动部署
```

推荐主图显示 `★ 推荐`；PDF 自动提取图显示“PDF 自动抓取”和页码，不带推荐星标。单篇 PDF 最多抓取 30 张图片，并过滤宽度小于 220、高度小于 160 或面积小于 60,000 像素的小图标。矢量图或被拆成复杂绘图指令的内容不一定能作为内嵌图片提取。

分类模型、配色提取与 PDF 处理位于 `scripts/process_submission.py`，网页代码位于 `site/`，二者相互独立。

## 首次部署

1. 创建公开仓库 `speng4610-cyber/scientific-figure-atlas`。
2. 推送本项目到仓库的 `main` 分支。
3. 在仓库 `Settings → Pages → Build and deployment → Source` 选择 **GitHub Actions**。
4. 在 Actions 页面运行 `Deploy GitHub Pages`，或再次推送 `site/` 内任意文件。

网站地址预计为：<https://speng4610-cyber.github.io/scientific-figure-atlas/>

## 本地预览和测试

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m http.server 8000 --directory site
```

然后访问 <http://127.0.0.1:8000>。静态网页不再需要 Flask 或 SQLite。
