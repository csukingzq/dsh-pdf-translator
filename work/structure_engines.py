"""Optional isolated extraction engines. Never translate or render with BabelDOC.

Run this file with the separately provisioned engine interpreter. The parent
passes filenames and page numbers only: no API credentials enter this worker.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

VERSION = 'extraction-adapter-v1'


def extract_evidence(source, numbers, cache, python=None, offline=False):
    key = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    target = Path(cache)/('engines-'+hashlib.sha256(json.dumps([VERSION,key,numbers]).encode()).hexdigest()+'.json')
    if target.exists():
        return json.loads(target.read_text('utf-8'))
    if not python or offline:
        return {'pages':{},'engines':[], 'available':False}
    result = subprocess.run([str(python), str(Path(__file__).resolve()), str(source),
        ','.join(map(str,numbers)), str(target)], capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=1800)
    if result.returncode or not target.exists():
        raise RuntimeError('结构解析工作进程失败：'+result.stderr[-2000:])
    return json.loads(target.read_text('utf-8'))


def babeldoc_pages(source, numbers, folder):
    from importlib.metadata import version
    if version('babeldoc') != '0.6.4':
        raise RuntimeError('解析适配层要求 babeldoc==0.6.4')
    from babeldoc.docvision.doclayout import DocLayoutModel
    from babeldoc.format.pdf.translation_config import TranslationConfig
    from babeldoc.format.pdf import high_level
    from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas

    class Parsed(BaseException):
        pass

    captured = {}
    original = StylesAndFormulas.process
    def stop_after_parsing(self, document, *args, **kwargs):
        result = original(self, document, *args, **kwargs)
        for page in document.page:
            media = page.mediabox.box
            width, height = media.x2-media.x, media.y2-media.y
            paragraphs = []
            for paragraph in page.pdf_paragraph:
                box = paragraph.box
                if not box or not paragraph.unicode:
                    continue
                paragraphs.append(dict(source_text=paragraph.unicode,
                    bbox=[(box.x-media.x)/width,1-(box.y2-media.y)/height,
                          (box.x2-media.x)/width,1-(box.y-media.y)/height],
                    role_candidate=paragraph.layout_label, source='babeldoc-0.6.4'))
            captured[str(page.page_number+1)] = paragraphs
        # Deliberately stop before term extraction, translation and typesetting.
        raise Parsed()
    StylesAndFormulas.process = stop_after_parsing
    try:
        config = TranslationConfig(translator=None, input_file=str(source), lang_in='en', lang_out='zh',
            doc_layout_model=DocLayoutModel.load_onnx(), pages=','.join(map(str,numbers)),
            working_dir=str(folder), output_dir=str(folder), skip_translation=True,
            auto_extract_glossary=False, use_rich_pbar=False, skip_scanned_detection=True)
        try:
            high_level.translate(config)
        except Parsed:
            pass
    finally:
        StylesAndFormulas.process = original
    if not captured:
        raise RuntimeError('BabelDOC 未产生段落证据')
    return captured


def ocr_page(page, engine):
    import numpy as np
    pix = page.get_pixmap(matrix=__import__('pymupdf').Matrix(2,2), alpha=False)
    rgb = np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
    regions=[]
    for result in engine.predict(rgb):
        data = result.json
        if isinstance(data,str):
            data=json.loads(data)
        data=data.get('res',data)
        for text,box,score in zip(data['rec_texts'],data['rec_boxes'],data['rec_scores']):
            regions.append(dict(source_text=text, bbox=[float(box[0])/pix.width,float(box[1])/pix.height,
                float(box[2])/pix.width,float(box[3])/pix.height],confidence=float(score),source='paddleocr'))
    return regions


def worker(source, numbers, output):
    import pymupdf
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with pymupdf.open(source) as pdf:
        native=[n for n in numbers if len(pdf[n-1].get_text().strip())>=40]
        scanned=[n for n in numbers if n not in native]
        pages=babeldoc_pages(source,native,output.parent/'engine-work') if native else {}
        engines=['babeldoc-0.6.4'] if native else []
        if scanned:
            os.environ.setdefault('PADDLE_PDX_MODEL_SOURCE', 'modelscope')
            from paddleocr import PaddleOCR
            engine=PaddleOCR(use_doc_orientation_classify=False,use_doc_unwarping=False,
                            use_textline_orientation=False,device='cpu')
            for n in scanned:
                pages[str(n)]=ocr_page(pdf[n-1],engine)
            engines.append('paddleocr')
    temp=output.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(pages=pages,engines=engines,available=True,version=VERSION),
                               ensure_ascii=False),'utf-8')
    temp.replace(output)


if __name__ == '__main__':
    worker(sys.argv[1], [int(n) for n in sys.argv[2].split(',')], sys.argv[3])
