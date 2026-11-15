from types import SimpleNamespace as NS
import unittest

from structured_layout import StructuredLayoutModel, split_structured_text


def span(text, y, font='Times', size=10):
    return {'text': text, 'origin': (10, y), 'size': size, 'font': font}


def native(spans, rotation=0):
    return NS(rotation=rotation, get_text=lambda _: {
        'blocks': [{'lines': [{'spans': spans}]}]})


def layout():
    return NS(names={0: 'plain text', 1: 'isolate_formula'}, boxes=[
        NS(cls=0, xyxy=(0, 0, 100, 50), conf=0.5),
        NS(cls=1, xyxy=(0, 55, 100, 70), conf=0.9)])


class StructuredLayoutTest(unittest.TestCase):
    def test_input_output_algorithm_rows(self):
        result = layout()
        page = native([span('Input: parameters', 10), span('Output: network', 21),
                       span('for each layer', 32), span('end for', 43)])
        self.assertEqual(split_structured_text(result, page), 1)
        self.assertEqual(len(result.boxes), 5)

    def test_numbered_loop_rows(self):
        result = layout()
        page = native([span('1: repeat', 10), span('2: sample x', 21),
                       span('3: update parameters', 32), span('4: until converged', 43)])
        self.assertEqual(split_structured_text(result, page), 1)
        self.assertEqual(len(result.boxes), 5)

    def test_algorithm_rows_ignore_raised_radicals_and_subscripts(self):
        page = native([span('Require: parameters', 10), span('Require: input', 21),
                       span('while updating', 32), span('root', 25, 'CMSY10'),
                       span('i', 35, 'CMMI7', 7), span('return result', 43)])
        result = layout()
        equation = result.boxes[1]
        self.assertEqual(split_structured_text(result, page), 1)
        self.assertEqual(len(result.boxes), 5)
        self.assertIs(result.boxes[-1], equation)
        for baseline, box in zip((10, 21, 32, 43), result.boxes):
            self.assertLess(box.xyxy[1], baseline)
            self.assertGreater(box.xyxy[3], baseline)
        for a, b in zip(result.boxes[:3], result.boxes[1:4]):
            self.assertEqual(a.xyxy[3], b.xyxy[1])

    def test_theorem_rows_separate_but_ordinary_paragraph_stays(self):
        for heading in ('Theorem 4.1.', 'Corollary 4.2.', 'Lemma 2.', 'Proposition 1.'):
            result = layout()
            self.assertEqual(split_structured_text(result, native([
                span(heading + ' Assume gradients', 10), span('are bounded', 21)])), 1)
            self.assertEqual(len(result.boxes), 3)
        result = layout()
        original = result.boxes[:]
        self.assertEqual(split_structured_text(result, native([
            span('Our Theorem 4.1 implies', 10), span('a useful bound', 21)])), 0)
        self.assertEqual(result.boxes, original)

    def test_wrapper_skips_rotation_and_merges_diagnostics(self):
        result = layout()
        page = NS(page_number=3)
        doc = {3: native([span('Theorem 1. Assume', 10), span('bounded gradients', 21)])}
        model = NS(stride=32, handle_document=lambda *a: iter([(page, result)]),
                   diagnostics=lambda: {'layoutCorrectedBoxes': 2})
        wrapper = StructuredLayoutModel(model)
        self.assertEqual(list(wrapper.handle_document([], doc, None, None)), [(page, result)])
        self.assertEqual(wrapper.diagnostics(), {'layoutCorrectedBoxes': 2,
                         'structuredLayoutPages': [4], 'structuredLayoutBlocks': 1})
        self.assertEqual(wrapper.stride, 32)
        doc[3].rotation = 90
        result = layout()
        list(wrapper.handle_document([], doc, None, None))
        self.assertEqual(len(result.boxes), 2)


if __name__ == '__main__':
    unittest.main()
