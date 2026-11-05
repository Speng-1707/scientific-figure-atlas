# 科研图鉴 Figure Atlas

以 GitHub 为长期存储的科研图片共享图库：GitHub Pages 提供网页，Cloudflare Worker + KV 接收免登录临时上传，GitHub Actions 自动分类、提取完整代表色板，并把正式图片和元数据保存回仓库。

## 投稿

1. 打开网站，选择“免登录上传”或“完整投稿”。
2. 免登录上传只要求一张图片。提交后会生成私密管理链接；创建者可以保存链接继续编辑，也可以把它分享给可信的共同贡献者。
3. 完整投稿可以填写投稿人信息、1–5 星评分、推荐理由和论文 PDF。
4. 完整投稿会创建 GitHub Issue；免登录投稿由定时工作流在约 5 分钟内同步到 GitHub。

公开仓库中的图片、论文、Issue 和处理结果对所有人可见。请只上传有权公开分享的材料。

## 自动处理流程

```text
免登录上传 → Cloudflare KV 临时暂存 → GitHub OIDC 定时同步
或 GitHub Issue 完整投稿
  → 校验 GitHub 附件和文件大小
  → 规范化图片并删除 EXIF
  → 关键词分类（或采用投稿者选择）
  → 提取最多 18 个代表色（彩色与有意义的中性色）
  → PDF 仅作为论文附件保存，不自动抓取其中图片
  → 保存到 site/assets 和 data/figures.json
  → GitHub Pages 自动部署
```

Cloudflare 不保存 GitHub 写入密钥。同步工作流使用仅在单次 Action 中短暂有效、并限定本仓库的 OIDC 身份；图片同步成功后会从 KV 临时区删除，GitHub 是最终存储位置。

每张投稿图片显示投稿者选择的 1–5 星评分。网页提供单张删除和批量删除；点击后会创建 GitHub 删除请求，只有仓库所有者、成员或协作者提交的请求才会由工作流自动执行，以免公开网页被他人恶意删除。

分类与配色模型位于 `scripts/process_submission.py`，免登录同步位于 `scripts/process_anonymous.py`，Cloudflare 接口位于 `worker/`，网页代码位于 `site/`，各模块相互独立。

## 首次部署

1. 创建公开仓库 `Speng-1707/scientific-figure-atlas`。
2. 推送本项目到仓库的 `main` 分支。
3. 在仓库 `Settings → Pages → Build and deployment → Source` 选择 **GitHub Actions**。
4. 在 Actions 页面运行 `Deploy GitHub Pages`，或再次推送 `site/` 内任意文件。

网站地址：<https://speng-1707.github.io/scientific-figure-atlas/>

## 本地预览和测试

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m http.server 8000 --directory site
```

然后访问 <http://127.0.0.1:8000>。静态网页不再需要 Flask 或 SQLite。
