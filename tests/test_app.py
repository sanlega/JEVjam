"""Servidor de la app: validación de opciones y rutas (sin audio ni red)."""
import pytest

from jevjam.app import parse_config, review_text


def test_parse_config_converts_json_types():
    cfg = parse_config({"input": "mic", "device": 3, "channel": "1", "bpm": "100", "bars": "8", "key": "C major"})
    assert (cfg.device, cfg.channel, cfg.bpm, cfg.bars, cfg.fixed_key()) == ("3", 1, 100.0, 8, (0, "major"))


def test_parse_config_defaults_are_auto():
    cfg = parse_config({"input": "demo", "bpm": None, "key": "", "bars": ""})
    assert cfg.bpm is None and cfg.key is None and cfg.bars is None


@pytest.mark.parametrize("body,msg", [
    ({"input": "demo", "key": "H minor"}, "tonalidad"),
    ({"input": "demo", "bpm": 900}, "bpm"),
    ({"input": "/no/existe.wav"}, "no existe"),
    ({"input": "demo", "rm_rf": True}, "desconocidas"),
])
def test_parse_config_rejects_bad_input(body, msg):
    with pytest.raises(ValueError, match=msg):
        parse_config(body)


@pytest.mark.parametrize("folder", ["/etc", "recordings/../..", ""])
def test_review_only_inside_recordings(folder):
    with pytest.raises(ValueError):
        review_text(folder)
