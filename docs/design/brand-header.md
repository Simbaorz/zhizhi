# 致知品牌区域

使用内置 ImageGen 生成背景素材，保留已有的「知」字图标。三个独立前端各自持有相同背景，避免跨工程的资源依赖。

- `zhizhi-web/src/assets/zhizhi-brand-background.png`
- `zhizhi-admin-web/src/assets/zhizhi-brand-background.png`
- `zhizhi-portal-admin-web/src/assets/zhizhi-brand-background.png`

图标与文字左对齐；浅紫背景右侧使用半透明书页、连接线和知识节点，文字由实际 HTML 渲染。

## ImageGen prompt

```text
Use case: stylized-concept. Asset type: production background artwork for the narrow top-left brand header of a Chinese enterprise knowledge Agent app named Zhizhi (格物致知). Generate only the decorative background asset, NOT a screenshot, NOT a logo, no text. Wide landscape composition about 3:1. Background ivory-white blending into pale lavender. Keep left 65% very calm and bright, suitable for a violet logo and dark typography overlaid in real HTML. On the far right, an elegant small arrangement of translucent folded book-page planes, a few fine curved paths and tiny interconnected violet points, suggesting exploring knowledge and turning it into action. Elegant restrained editorial sophistication, soft dimensional light, crisp understated geometry with a faint cool teal accent. Violet #6157d9, pale lavender #ede8ff, pearl white, extremely subtle teal. Rich but clean, thoughtful, not childish. Artwork must still look refined cropped into a 264x104px brand header. Avoid grids, checkerboards, giant circles, sci-fi neon, busy particles, harsh purple fields, noise, literal books with readable text, any lettering, UI controls, watermark, logo, border, mockup framing. Full bleed opaque background.
```
