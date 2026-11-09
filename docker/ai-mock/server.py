"""Test-only OpenAI HTTP substitute. Never included in the application/production Compose stack."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


def evidence(text, fact):
    return {"text": text, "fact_ids": [fact['id']]}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        facts = json.loads(body['messages'][1]['content'].split('```json\n')[1].split('\n```')[0])
        numeric = [f for f in facts if isinstance(f['value'], (int, float))]
        a, b = numeric[:2]
        ea = evidence(f"{a['label']}: {a['value']}.", a)
        eb = evidence(f"{b['label']}: {b['value']}.", b)
        if body['response_format']['json_schema']['name'] == 'signal_brief':
            content = {'headline': 'Vegetation is below its seasonal range.', 'summary': ea,
                       'explanations': [{'title': title, 'assessment': 'possible', 'supporting': [eb],
                                         'contradicting': [{'text': 'No stored evidence rules this out.', 'fact_ids': []}]} for title in ('Irrigation interruption', 'Management work')],
                       'checklist': [{'text': text, 'fact_ids': []} for text in ('Check irrigation valves.', 'Look for bare patches.', 'Check recent maintenance work.')], 'data_gaps': []}
        else:
            content = {'headline': 'Overview of stored operational figures.', 'paragraphs': [ea, eb], 'watch_items': []}
        payload = json.dumps({'choices': [{'message': {'content': json.dumps(content)}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 100}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
