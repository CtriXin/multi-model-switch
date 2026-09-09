"""Attachment content compatibility, public diagnostics and prompt delivery."""
import base64
import json

import pytest

from mms_web.errors import WebError
from mms_web.files import FileService, TEXT_LIMIT


@pytest.mark.parametrize("name", ["数据.json", "events.jsonl", "settings.JSON", "plain-no-extension"])
def test_json_is_text_and_reaches_prompt_unchanged(tmp_path, name):
    files = FileService(None, tmp_path)
    content = json.dumps({"项目": "上传验收", "items": [1, 2, 3]}, ensure_ascii=False)
    item = files.upload({"name": name, "data": base64.b64encode(content.encode()).decode()})
    assert item["mimeType"] == "text/plain"
    assert files.preview_attachment(item["id"])["content"] == content
    images, attachments, prompt = files.prepare([item["id"]], "", [])
    assert images == [] and attachments == [item]
    assert content in prompt and name in json.loads(prompt.split("name=", 1)[1].split(">", 1)[0])


@pytest.mark.parametrize("data,code,message", [
    (b'{"data":"' + b'x' * TEXT_LIMIT + b'"}', "ATTACHMENT_TEXT_TOO_LARGE", "超过 1 MB"),
    ('{"项目":"上传"}'.encode("utf-16"), "ATTACHMENT_ENCODING", "UTF-16"),
    ('{"项目":"上传"}'.encode("utf-32"), "ATTACHMENT_ENCODING", "UTF-32"),
    ('{"项目":"上传"}'.encode("gbk"), "ATTACHMENT_ENCODING", "另存为 UTF-8"),
    (b'PK\x03\x04\0binary', "ATTACHMENT_UNSUPPORTED", "二进制"),
])
def test_failure_names_actual_reason_without_storing_attachment(tmp_path, data, code, message):
    files = FileService(None, tmp_path)
    with pytest.raises(WebError) as error:
        files.upload({"name": "data.json", "data": base64.b64encode(data).decode()})
    assert error.value.code == code
    assert message in error.value.message
    assert not files.root.exists()


def test_utf8_bom_and_one_mb_boundary(tmp_path):
    files = FileService(None, tmp_path)
    data = b'\xef\xbb\xbf{"key":"' + b'x' * (TEXT_LIMIT - 13) + b'"}'
    assert len(data) == TEXT_LIMIT
    item = files.upload({"name": "bom.json", "data": base64.b64encode(data).decode()})
    assert files.preview_attachment(item["id"])["content"] == data.decode("utf-8")
