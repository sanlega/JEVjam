# Vídeo brag de JEVjam

- **Fecha**: 2026-09-30 16:16
- **Agente**: claude
- **Rama**: claude/trusting-galileo-loq4uk @ 70fac22

## Hecho
- brag-output/brag.mp4 (1920x1080, 22,4 s, -13,6 LUFS), brag.jpg (póster, horneado como frame 0), share-copy.txt, brag-plan.md.
- Banda sonora generada con los generadores reales (Band.render_bar) y SynthEngine; humano sintético con render_human. Am-G-F-E a 100 BPM; la banda entra en el pulso 2 (chiste del modo reactivo).
- Vídeo: HTML con render(t) puro + Playwright fotograma a fotograma + ffmpeg (imageio-ffmpeg). Scripts en brag-output/work/ (no versionados).

## Retro
- Funcionó: reutilizar tokens CSS de la app y la captura index.html?preview; hojas de contacto con xstack para revisar fotogramas.
- Falló: descargar fuentes por raw.githubusercontent (bloqueado); sirvió un clon sparse de google/fonts.
