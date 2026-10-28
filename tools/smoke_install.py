"""Exercise a fresh Docker install, including real speech and an MP3 export."""
import argparse
import io
import json
import time
import urllib.parse
import urllib.request
import wave


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--studio', default='http://127.0.0.1:7870')
    parser.add_argument('--silero', default='http://127.0.0.1:7866')
    args = parser.parse_args()

    def request(base, path, payload=None, raw=False):
        body = None if payload is None else json.dumps(payload, ensure_ascii=True).encode('utf-8')
        req = urllib.request.Request(base + path, data=body, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=600) as response:
            data = response.read()
        return data if raw else json.loads(data)

    assert request(args.studio, '/api/health')
    assert request(args.silero, '/health')['ok']
    assert b'<html' in request(args.studio, '/studio/', raw=True).lower()
    text = 'Привет. Проверка установки и сохранения аудио.'
    data = request(args.silero, '/v1/tts', {'text': text, 'speaker': 'baya', 'return_file': True}, raw=True)
    with wave.open(io.BytesIO(data)) as wav:
        assert wav.getnframes() > wav.getframerate() // 2
        assert wav.getnchannels() >= 1
    created = request(args.studio, '/api/projects', {'name': 'Install verification', 'initial_text': text})
    pid = created['project']['id']
    query = '?project_id=' + urllib.parse.quote(pid)
    project = request(args.studio, '/api/chunks/split' + query, {'text': text, 'max_chars': 200})
    chunks = project['chunks']
    queued = request(args.studio, '/api/queue/generate' + query, {'chunk_ids': [c['id'] for c in chunks]})

    def wait_tasks(ids):
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            queue = request(args.studio, '/api/queue' + query)['queue']
            selected = [task for task in queue if task['id'] in ids]
            failed = [t for t in selected if t['status'] in ('failed', 'error', 'cancelled')]
            if failed:
                raise RuntimeError(json.dumps(failed, ensure_ascii=False))
            if len(selected) == len(ids) and all(t['status'] in ('done', 'completed') for t in selected):
                return selected
            time.sleep(2)
        raise TimeoutError('Generation/export did not complete in 10 minutes')

    wait_tasks([task['id'] for task in queued['queued_tasks']])
    project = request(args.studio, '/api/projects/' + pid)
    path = project['chunks'][0]['audio_path']
    assert len(request(args.studio, '/api/audio?path=' + urllib.parse.quote(path), raw=True)) > 1000
    exported = request(args.studio, '/api/queue/export' + query, {'audio_format': 'mp3'})
    result = wait_tasks([exported['queued_task']['id']])
    mp3 = request(args.studio, '/api/audio?path=' + urllib.parse.quote(result[0]['result_path']), raw=True)
    assert len(mp3) > 1000
    assert mp3.startswith(b'ID3') or mp3[0] == 0xff
    print(json.dumps({'ok': True, 'project_id': pid, 'silero_wav_bytes': len(data), 'mp3_bytes': len(mp3), 'export': result}, ensure_ascii=False))


if __name__ == '__main__':
    main()
