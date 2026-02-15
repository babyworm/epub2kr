"""Unit tests for translation services."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from epub2kr.services import (
    get_service,
    list_services,
    GoogleTranslateService,
    DeepLService,
    OpenAIService,
    OllamaService,
)


class TestServiceFactory:
    """Tests for service factory functions."""

    def test_get_service_google_without_args(self):
        """Test that get_service('google') works without arguments."""
        service = get_service('google')
        assert isinstance(service, GoogleTranslateService)
        assert service.name() == 'google'

    def test_get_service_unknown_raises_valueerror(self):
        """Test that get_service raises ValueError for unknown service."""
        with pytest.raises(ValueError) as exc_info:
            get_service('unknown')

        assert 'Unknown service' in str(exc_info.value)
        assert 'google' in str(exc_info.value)
        assert 'deepl' in str(exc_info.value)

    def test_list_services_returns_all_services(self):
        """Test that list_services returns all 4 services."""
        services = list_services()
        assert len(services) == 4
        assert 'google' in services
        assert 'deepl' in services
        assert 'openai' in services
        assert 'ollama' in services


class TestGoogleTranslateService:
    """Tests for Google Translate service."""

    def test_translate_empty_list_returns_empty(self):
        """Test that translating empty list returns empty list."""
        service = GoogleTranslateService()
        result = service.translate([], 'en', 'ko')
        assert result == []

    def test_translate_whitespace_only_returns_as_is(self):
        """Test that whitespace-only texts are returned unchanged."""
        service = GoogleTranslateService()

        with patch.object(service, '_translate_single') as mock_translate:
            result = service.translate(['  ', '\n', '\t'], 'en', 'ko')

            # _translate_single should not be called for whitespace
            mock_translate.assert_not_called()
            assert result == ['  ', '\n', '\t']

    def test_translate_with_mocked_http(self):
        """Test translation with mocked HTTP request."""
        service = GoogleTranslateService()

        # Mock response data: [[["translated text","original text"]]]
        mock_response = Mock()
        mock_response.json.return_value = [[["번역된 텍스트", "original text"]]]
        mock_response.raise_for_status = Mock()

        with patch('requests.get', return_value=mock_response) as mock_get:
            result = service.translate(['Hello world'], 'en', 'ko')

            assert result == ['번역된 텍스트']
            mock_get.assert_called_once()

            # Verify request parameters
            call_args = mock_get.call_args
            assert call_args.kwargs['params']['q'] == 'Hello world'
            assert call_args.kwargs['params']['sl'] == 'en'
            assert call_args.kwargs['params']['tl'] == 'ko'

    def test_translate_multiple_segments(self):
        """Test translation with multiple text segments in response."""
        service = GoogleTranslateService()

        # Mock response with multiple segments
        mock_response = Mock()
        mock_response.json.return_value = [[
            ["첫 번째 ", "First "],
            ["부분", "part"]
        ]]
        mock_response.raise_for_status = Mock()

        with patch('requests.get', return_value=mock_response):
            result = service.translate(['First part'], 'en', 'ko')

            # Should concatenate segments
            assert result == ['첫 번째 부분']

    def test_normalize_lang_code_mappings(self):
        """Test language code normalization."""
        service = GoogleTranslateService()

        assert service._normalize_lang_code('zh') == 'zh-CN'
        assert service._normalize_lang_code('zh-cn') == 'zh-CN'
        assert service._normalize_lang_code('zh-tw') == 'zh-TW'
        assert service._normalize_lang_code('en') == 'en'
        assert service._normalize_lang_code('ko') == 'ko'
        assert service._normalize_lang_code('ja') == 'ja'
        assert service._normalize_lang_code('unknown') == 'unknown'

    def test_error_handling_returns_original_text(self):
        """Test that errors return original text."""
        service = GoogleTranslateService()

        with patch('requests.get', side_effect=Exception('Network error')):
            result = service.translate(['Hello'], 'en', 'ko')

            # Should return original text on error
            assert result == ['Hello']

    def test_rate_limit_delay(self):
        """Test that rate limiting is applied for multiple texts."""
        service = GoogleTranslateService(rate_limit_delay=0.1)

        mock_response = Mock()
        mock_response.json.return_value = [[["번역", "text"]]]
        mock_response.raise_for_status = Mock()

        with patch('requests.get', return_value=mock_response):
            with patch('time.sleep') as mock_sleep:
                service.translate(['text1', 'text2'], 'en', 'ko')

                # Should sleep after each translation when len(texts) > 1
                assert mock_sleep.call_count == 2
                mock_sleep.assert_called_with(0.1)


class TestDeepLService:
    """Tests for DeepL service."""

    def test_raises_valueerror_without_api_key(self, monkeypatch):
        """Test that DeepL raises ValueError without API key."""
        # Remove environment variable
        monkeypatch.delenv('DEEPL_API_KEY', raising=False)

        with pytest.raises(ValueError) as exc_info:
            DeepLService()

        assert 'DeepL API key required' in str(exc_info.value)

    def test_raises_valueerror_without_api_key_param(self, monkeypatch):
        """Test that DeepL raises ValueError when both param and env are None."""
        monkeypatch.delenv('DEEPL_API_KEY', raising=False)

        with pytest.raises(ValueError) as exc_info:
            DeepLService(api_key=None)

        assert 'DEEPL_API_KEY' in str(exc_info.value)

    def test_accepts_api_key_from_param(self, monkeypatch):
        """Test that DeepL accepts API key from parameter."""
        monkeypatch.delenv('DEEPL_API_KEY', raising=False)

        # Mock deepl module
        mock_deepl = MagicMock()
        mock_translator = MagicMock()
        mock_deepl.Translator.return_value = mock_translator

        with patch.dict('sys.modules', {'deepl': mock_deepl}):
            service = DeepLService(api_key='test-key-123')
            assert service.api_key == 'test-key-123'
            assert service.name() == 'deepl'

    def test_accepts_api_key_from_env(self, monkeypatch):
        """Test that DeepL accepts API key from environment."""
        monkeypatch.setenv('DEEPL_API_KEY', 'env-key-456')

        # Mock deepl module
        mock_deepl = MagicMock()
        mock_translator = MagicMock()
        mock_deepl.Translator.return_value = mock_translator

        with patch.dict('sys.modules', {'deepl': mock_deepl}):
            service = DeepLService()
            assert service.api_key == 'env-key-456'


class TestOpenAIService:
    """Tests for OpenAI service."""

    def test_raises_valueerror_without_api_key(self, monkeypatch):
        """Test that OpenAI raises ValueError without API key."""
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)

        with pytest.raises(ValueError) as exc_info:
            OpenAIService()

        assert 'OpenAI API key required' in str(exc_info.value)

    def test_raises_valueerror_without_api_key_param(self, monkeypatch):
        """Test that OpenAI raises ValueError when both param and env are None."""
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)

        with pytest.raises(ValueError) as exc_info:
            OpenAIService(api_key=None)

        assert 'OPENAI_API_KEY' in str(exc_info.value)

    def test_accepts_api_key_from_param(self, monkeypatch):
        """Test that OpenAI accepts API key from parameter."""
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)

        # Mock openai module
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict('sys.modules', {'openai': mock_openai}):
            service = OpenAIService(api_key='test-key-123')
            assert service.api_key == 'test-key-123'
            assert service.name() == 'openai'

    def test_format_language_name(self, monkeypatch):
        """Test language code to name formatting."""
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)

        # Mock openai module
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = MagicMock()

        with patch.dict('sys.modules', {'openai': mock_openai}):
            service = OpenAIService(api_key='test-key')

            assert service._format_language_name('en') == 'English'
            assert service._format_language_name('zh') == 'Chinese'
            assert service._format_language_name('zh-cn') == 'Simplified Chinese'
            assert service._format_language_name('zh-tw') == 'Traditional Chinese'
            assert service._format_language_name('ko') == 'Korean'
            assert service._format_language_name('ja') == 'Japanese'
            assert service._format_language_name('unknown') == 'UNKNOWN'

    def test_custom_base_url(self, monkeypatch):
        """Test that custom base_url is passed to client."""
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)

        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict('sys.modules', {'openai': mock_openai}):
            service = OpenAIService(
                api_key='test-key',
                base_url='http://localhost:8000/v1'
            )

            # Verify OpenAI client was initialized with base_url
            mock_openai.OpenAI.assert_called_once()
            call_kwargs = mock_openai.OpenAI.call_args.kwargs
            assert call_kwargs['api_key'] == 'test-key'
            assert call_kwargs['base_url'] == 'http://localhost:8000/v1'


class TestOllamaService:
    """Tests for Ollama service."""

    def test_default_base_url(self):
        """Test that default base_url is correct."""
        service = OllamaService()
        assert service.base_url == 'http://localhost:11434'
        assert service.api_url == 'http://localhost:11434/api/generate'

    def test_custom_base_url(self):
        """Test that custom base_url is used."""
        service = OllamaService(base_url='http://custom:8080')
        assert service.base_url == 'http://custom:8080'
        assert service.api_url == 'http://custom:8080/api/generate'

    def test_default_model(self):
        """Test that default model is llama2."""
        service = OllamaService()
        assert service.model == 'llama2'

    def test_custom_model(self):
        """Test that custom model is used."""
        service = OllamaService(model='mistral')
        assert service.model == 'mistral'

    def test_clean_translation_removes_prefix(self):
        """Test that _clean_translation removes common prefixes."""
        service = OllamaService()

        assert service._clean_translation('Translation: 번역된 텍스트') == '번역된 텍스트'
        assert service._clean_translation('Here is the translation: 번역') == '번역'
        assert service._clean_translation('The translation is: 텍스트') == '텍스트'

        # Case insensitive
        assert service._clean_translation('TRANSLATION: 텍스트') == '텍스트'

    def test_clean_translation_removes_quotes(self):
        """Test that _clean_translation removes surrounding quotes."""
        service = OllamaService()

        assert service._clean_translation('"번역된 텍스트"') == '번역된 텍스트'
        assert service._clean_translation("'번역된 텍스트'") == '번역된 텍스트'

        # Don't remove partial quotes
        assert service._clean_translation('"partially quoted') == '"partially quoted'
        assert service._clean_translation('quoted"') == 'quoted"'

    def test_clean_translation_combined(self):
        """Test that _clean_translation handles prefix + quotes."""
        service = OllamaService()

        result = service._clean_translation('Translation: "번역된 텍스트"')
        assert result == '번역된 텍스트'

    def test_check_availability_success(self):
        """Test check_availability when Ollama is running."""
        service = OllamaService(model='llama2')

        mock_response = Mock()
        mock_response.json.return_value = {
            'models': [
                {'name': 'llama2:latest'},
                {'name': 'mistral:latest'}
            ]
        }
        mock_response.raise_for_status = Mock()

        with patch('requests.get', return_value=mock_response):
            assert service.check_availability() is True

    def test_check_availability_model_not_found(self):
        """Test check_availability when model is not available."""
        service = OllamaService(model='nonexistent')

        mock_response = Mock()
        mock_response.json.return_value = {
            'models': [
                {'name': 'llama2:latest'},
            ]
        }
        mock_response.raise_for_status = Mock()

        with patch('requests.get', return_value=mock_response):
            assert service.check_availability() is False

    def test_check_availability_connection_error(self):
        """Test check_availability when Ollama is not running."""
        service = OllamaService()

        with patch('requests.get', side_effect=Exception('Connection refused')):
            assert service.check_availability() is False

    def test_translate_empty_list(self):
        """Test that translating empty list returns empty list."""
        service = OllamaService()
        result = service.translate([], 'en', 'ko')
        assert result == []

    def test_translate_whitespace_only(self):
        """Test that whitespace-only texts are returned unchanged."""
        service = OllamaService()

        with patch.object(service, '_translate_single') as mock_translate:
            result = service.translate(['  ', '\n'], 'en', 'ko')

            mock_translate.assert_not_called()
            assert result == ['  ', '\n']

    def test_translate_error_returns_original(self):
        """Test that translation errors return original text."""
        service = OllamaService()

        with patch('requests.post', side_effect=Exception('API error')):
            result = service.translate(['Hello'], 'en', 'ko')

            assert result == ['Hello']

    def test_format_language_name(self):
        """Test language code to name formatting."""
        service = OllamaService()

        assert service._format_language_name('en') == 'English'
        assert service._format_language_name('zh') == 'Chinese'
        assert service._format_language_name('zh-cn') == 'Simplified Chinese'
        assert service._format_language_name('ko') == 'Korean'
        assert service._format_language_name('unknown') == 'UNKNOWN'
