"""
storage/json_writer.py 유닛 테스트.
"""
import json
from pathlib import Path

import pytest

from src.storage.json_writer import (
    build_document_path,
    get_saved_ids,
    load_all_documents_in_collection,
    load_documents,
    sanitize_job_function_dirname,
    save_document,
    save_documents,
    _sanitize_filename,
)


@pytest.fixture
def tmp_base(tmp_path: Path) -> Path:
    return tmp_path


class TestSanitizeFilename:
    def test_ascii_only(self):
        assert _sanitize_filename("indeed_Python_서울") == "indeed_Python_서울"

    def test_spaces_replaced(self):
        result = _sanitize_filename("백엔드 개발자")
        assert " " not in result

    def test_slashes_replaced(self):
        result = _sanitize_filename("a/b\\c")
        assert "/" not in result
        assert "\\" not in result


class TestSanitizeJobFunctionDirname:
    def test_normal_name_unchanged(self):
        assert sanitize_job_function_dirname("Backend Engineer") == "Backend Engineer"

    def test_slash_replaced_with_dot(self):
        assert (
            sanitize_job_function_dirname("Data Labeling / Annotation Specialist")
            == "Data Labeling . Annotation Specialist"
        )

    def test_devops_slash(self):
        assert (
            sanitize_job_function_dirname("DevOps / Platform Engineer")
            == "DevOps . Platform Engineer"
        )

    def test_no_slash_path_separator_left(self):
        result = sanitize_job_function_dirname("QA / Test Engineer")
        assert "/" not in result


class TestBuildDocumentPath:
    def test_normal_job_function(self, tmp_base: Path):
        path = build_document_path(
            collection_name="raw_job_postings",
            job_function_name="Backend Engineer",
            source_name="saramin",
            crawl_date="2026-08-03",
            source_job_id="54487301",
            base_dir=str(tmp_base),
        )
        assert path == (
            tmp_base
            / "raw_job_postings"
            / "Backend Engineer"
            / "saramin"
            / "2026-08-03_54487301.json"
        )

    def test_slash_in_job_function(self, tmp_base: Path):
        path = build_document_path(
            collection_name="job_postings",
            job_function_name="Data Labeling / Annotation Specialist",
            source_name="remotive",
            crawl_date="2026-08-03",
            source_job_id="98765",
            base_dir=str(tmp_base),
        )
        assert path == (
            tmp_base
            / "job_postings"
            / "Data Labeling . Annotation Specialist"
            / "remotive"
            / "2026-08-03_98765.json"
        )
        # 폴더 세그먼트에 raw '/' 가 섞이면 안 된다
        assert "Data Labeling / Annotation Specialist" not in path.parts


class TestSaveDocument:
    def test_creates_file_at_new_path(self, tmp_base: Path):
        doc = {
            "id": "abc",
            "source_name": "indeed",
            "source_job_id": "jk1",
            "job_function_name": "Backend Engineer",
        }
        path = save_document(
            doc,
            "raw_job_postings",
            crawl_date="2026-07-24",
            base_dir=str(tmp_base),
        )
        assert path.exists()
        assert path == (
            tmp_base
            / "raw_job_postings"
            / "Backend Engineer"
            / "indeed"
            / "2026-07-24_jk1.json"
        )

    def test_content_is_valid_json(self, tmp_base: Path):
        doc = {
            "id": "abc",
            "value": 42,
            "source_name": "indeed",
            "source_job_id": "jk1",
            "job_function_name": "Backend Engineer",
        }
        path = save_document(
            doc,
            "raw_job_postings",
            crawl_date="2026-07-24",
            base_dir=str(tmp_base),
        )
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["value"] == 42

    def test_directory_created(self, tmp_base: Path):
        doc = {
            "id": "x",
            "source_name": "saramin",
            "source_job_id": "1",
            "job_function_name": "Backend Engineer",
        }
        path = save_document(
            doc,
            "new_collection",
            crawl_date="2099-01-01",
            base_dir=str(tmp_base),
        )
        assert path.parent.exists()


class TestSaveDocuments:
    def test_saves_one_file_per_document(self, tmp_base: Path):
        docs = [
            {
                "id": "1",
                "source_name": "indeed",
                "source_job_id": "jk1",
                "job_function_name": "Backend Engineer",
            },
            {
                "id": "2",
                "source_name": "indeed",
                "source_job_id": "jk2",
                "job_function_name": "Backend Engineer",
            },
        ]
        save_documents(
            docs,
            "raw_job_postings",
            crawl_date="2026-07-24",
            base_dir=str(tmp_base),
        )
        root = tmp_base / "raw_job_postings" / "Backend Engineer" / "indeed"
        assert (root / "2026-07-24_jk1.json").exists()
        assert (root / "2026-07-24_jk2.json").exists()

    def test_job_function_arg_used_when_doc_lacks_field(self, tmp_base: Path):
        docs = [
            {"id": "1", "source_name": "jumpit", "source_job_id": "pos1"},
        ]
        path = save_documents(
            docs,
            "raw_job_postings",
            crawl_date="2026-08-03",
            base_dir=str(tmp_base),
            job_function_name="Backend Engineer",
        )
        assert "Backend Engineer" in path.parts
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["job_function_name"] == "Backend Engineer"

    def test_slash_job_function_path(self, tmp_base: Path):
        docs = [
            {
                "id": "1",
                "source_name": "remotive",
                "source_job_id": "98765",
            },
        ]
        path = save_documents(
            docs,
            "raw_job_postings",
            crawl_date="2026-08-03",
            base_dir=str(tmp_base),
            job_function_name="Data Labeling / Annotation Specialist",
        )
        assert path == (
            tmp_base
            / "raw_job_postings"
            / "Data Labeling . Annotation Specialist"
            / "remotive"
            / "2026-08-03_98765.json"
        )
        assert path.exists()

    def test_deduplication_skips_existing_file(self, tmp_base: Path):
        doc1 = {
            "id": "A",
            "source_name": "indeed",
            "source_job_id": "jk1",
            "job_function_name": "Backend Engineer",
            "raw_text": "v1",
        }
        doc2 = {
            "id": "B",
            "source_name": "indeed",
            "source_job_id": "jk2",
            "job_function_name": "Backend Engineer",
        }

        save_documents(
            [doc1],
            "raw_job_postings",
            crawl_date="2026-07-24",
            base_dir=str(tmp_base),
        )
        save_documents(
            [doc1, doc2],
            "raw_job_postings",
            crawl_date="2026-07-24",
            base_dir=str(tmp_base),
        )

        root = tmp_base / "raw_job_postings" / "Backend Engineer" / "indeed"
        assert len(list(root.glob("*.json"))) == 2
        # 기존 파일은 덮어쓰지 않음
        loaded = json.loads((root / "2026-07-24_jk1.json").read_text(encoding="utf-8"))
        assert loaded["raw_text"] == "v1"

    def test_returns_saved_path(self, tmp_base: Path):
        docs = [
            {
                "id": "z",
                "source_name": "saramin",
                "source_job_id": "99",
                "job_function_name": "Backend Engineer",
            },
        ]
        path = save_documents(
            docs, "col", crawl_date="2026-07-24", base_dir=str(tmp_base),
        )
        assert path.exists()


class TestLoadDocuments:
    def test_returns_empty_list_for_missing_file(self, tmp_base: Path):
        result = load_documents(
            "no_collection", "no_file", "2026-07-24", str(tmp_base),
        )
        assert result == []

    def test_load_by_new_path_components(self, tmp_base: Path):
        docs = [
            {
                "id": "1",
                "source_name": "indeed",
                "source_job_id": "jk1",
                "job_function_name": "Backend Engineer",
                "title": "BE",
            },
        ]
        save_documents(
            docs,
            "raw_job_postings",
            crawl_date="2026-07-24",
            base_dir=str(tmp_base),
        )
        loaded = load_documents(
            "raw_job_postings",
            filename="2026-07-24_jk1",
            crawl_date="2026-07-24",
            base_dir=str(tmp_base),
            job_function_name="Backend Engineer",
            source_name="indeed",
            source_job_id="jk1",
        )
        assert len(loaded) == 1
        assert loaded[0]["title"] == "BE"


class TestGetSavedIds:
    def test_returns_natural_keys(self, tmp_base: Path):
        docs = [
            {
                "id": "1",
                "source_name": "indeed",
                "source_job_id": "jk1",
                "job_function_name": "Backend Engineer",
            },
            {
                "id": "2",
                "source_name": "indeed",
                "source_job_id": "jk2",
                "job_function_name": "Backend Engineer",
            },
        ]
        save_documents(
            docs,
            "raw_job_postings",
            crawl_date="2026-07-24",
            base_dir=str(tmp_base),
        )
        ids = get_saved_ids("raw_job_postings", str(tmp_base))
        assert ("indeed", "jk1") in ids
        assert ("indeed", "jk2") in ids

    def test_empty_when_no_data(self, tmp_base: Path):
        ids = get_saved_ids("raw_job_postings", str(tmp_base))
        assert ids == set()

    def test_load_all_across_functions(self, tmp_base: Path):
        save_documents(
            [
                {
                    "id": "1",
                    "source_name": "indeed",
                    "source_job_id": "a",
                    "job_function_name": "Backend Engineer",
                },
            ],
            "raw_job_postings",
            crawl_date="2026-08-03",
            base_dir=str(tmp_base),
        )
        save_documents(
            [
                {
                    "id": "2",
                    "source_name": "jumpit",
                    "source_job_id": "b",
                },
            ],
            "raw_job_postings",
            crawl_date="2026-08-03",
            base_dir=str(tmp_base),
            job_function_name="Frontend Engineer",
        )
        all_docs = load_all_documents_in_collection("raw_job_postings", str(tmp_base))
        assert len(all_docs) == 2
