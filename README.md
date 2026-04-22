# PDF---OCR
transforma pdf em OCR pesquisavel

## Pipeline rápido (com DPI reduzido)

Adicionado CLI `ocr_pipeline.py` com foco em velocidade.

### Requisitos
- `ocrmypdf`
- `tesseract`
- `ghostscript` (`gs`) para reduzir DPI no modo `fast`
- `pdftotext` (opcional, detecta PDF já pesquisável)

### Uso rápido
```bash
python3 ocr_pipeline.py process ./entrada -o ./saida --mode fast --dpi-fast 120 --workers 4 --lang por
```

### Benchmark rápido
```bash
python3 ocr_pipeline.py benchmark ./entrada -o ./saida_bench --mode fast --dpi-fast 120 --workers 4
```

### Modos
- `fast` (padrão): downsample de DPI + OCR otimizado para velocidade
- `balanced`: equilíbrio entre tempo e qualidade
- `accurate`: maior qualidade (mais lento)

Saída: `run_summary.json` com tempo por arquivo e resumo total.
