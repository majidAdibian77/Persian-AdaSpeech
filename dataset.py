import json
import math
from operator import sub
import os

import numpy as np
from torch.utils.data import Dataset

from text import text_to_sequence
from utils.tools import pad_1D, pad_2D


class Dataset(Dataset):
    def __init__(
        self, filename, preprocess_config, train_config, sort=False, drop_last=False
    ):
        self.dataset_name = preprocess_config["dataset"]
        self.preprocessed_path = preprocess_config["path"]["preprocessed_path"]
        self.cleaners = preprocess_config["preprocessing"]["text"]["text_cleaners"]
        self.batch_size = train_config["optimizer"]["batch_size"]
        self.open_set_speaker = preprocess_config['open_set_speaker']

        self.basename, self.speaker, self.text = self.process_meta(
            filename
        )
        if not self.open_set_speaker:
            with open(os.path.join(self.preprocessed_path, "speakers.json")) as f:
                self.speaker_map = json.load(f)
            
        self.sort = sort
        self.drop_last = drop_last
        self.count = 0
        
    def __len__(self):
        return len(self.text)

    def __getitem__(self, idx):
        basename = self.basename[idx]
        speaker_id = self.speaker[idx]
        if not self.open_set_speaker:
            speaker = self.speaker_map[speaker_id]
        else:
            speaker_embedding_path = os.path.join(
                self.preprocessed_path,
                "speaker_embedding",
                "{}-{}.npy".format(speaker_id, basename),
            )
            speaker = np.load(speaker_embedding_path).astype(np.float32)
        phone = np.array(text_to_sequence(self.text[idx], self.cleaners))
        mel_path = os.path.join(
            self.preprocessed_path,
            "mel",
            "{}-mel-{}.npy".format(speaker_id, basename),
        )
        mel = np.load(mel_path)
        pitch_path = os.path.join(
            self.preprocessed_path,
            "pitch",
            "{}-pitch-{}.npy".format(speaker_id, basename),
        )
        pitch = np.load(pitch_path)
        energy_path = os.path.join(
            self.preprocessed_path,
            "energy",
            "{}-energy-{}.npy".format(speaker_id, basename),
        )
        energy = np.load(energy_path)
        duration_path = os.path.join(
            self.preprocessed_path,
            "duration",
            "{}-duration-{}.npy".format(speaker_id, basename),
        )
        duration = np.load(duration_path)
        avg_mel_ph_path = os.path.join(
            self.preprocessed_path,
            "avg_mel_phon",
            "{}-avg_mel-{}.npy".format(speaker_id, basename),
        )

        avg_mel_ph = np.load(avg_mel_ph_path)

        sample = {
            "id": basename,
            "speaker": speaker,
            "text": phone,
            "mel": mel,
            "pitch": pitch,
            "energy": energy,
            "duration": duration,
            "avg_mel_ph": avg_mel_ph,
        }

        return sample

    def process_meta(self, filename):
        with open(
            os.path.join(self.preprocessed_path, filename), "r", encoding="utf-8"
        ) as f:
            name = []
            speaker = []
            text = []
            for line in f.readlines():
                n, s, t = line.strip("\n").split("|")
                name.append(n)
                speaker.append(s)
                text.append(t)
                
            return name, speaker, text

    def reprocess(self, data, idxs):
        ids = [data[idx]["id"] for idx in idxs]
        speakers = [data[idx]["speaker"] for idx in idxs]
        texts = [data[idx]["text"] for idx in idxs]
        mels = [data[idx]["mel"] for idx in idxs]
        pitches = [data[idx]["pitch"] for idx in idxs]
        energies = [data[idx]["energy"] for idx in idxs]
        durations = [data[idx]["duration"] for idx in idxs]
        avg_mel_phs = [data[idx]["avg_mel_ph"] for idx in idxs]

        text_lens = np.array([text.shape[0] for text in texts])
        mel_lens = np.array([mel.shape[0] for mel in mels])

        speakers = np.array(speakers)
        texts = pad_1D(texts)
        mels = pad_2D(mels)
        pitches = pad_1D(pitches)
        energies = pad_1D(energies)
        durations = pad_1D(durations)
        avg_mel_phs = pad_2D(avg_mel_phs)

        return (
            ids,
            speakers,
            texts,
            text_lens,
            max(text_lens),
            mels,
            mel_lens,
            max(mel_lens),
            pitches,
            energies,
            durations,
            avg_mel_phs
        )

    def collate_fn(self, data):
        data_size = len(data)

        if self.sort:
            len_arr = np.array([d["text"].shape[0] for d in data])
            idx_arr = np.argsort(-len_arr)
        else:
            idx_arr = np.arange(data_size)

        tail = idx_arr[len(idx_arr) - (len(idx_arr) % self.batch_size) :]
        idx_arr = idx_arr[: len(idx_arr) - (len(idx_arr) % self.batch_size)]
        idx_arr = idx_arr.reshape((-1, self.batch_size)).tolist()
        if not self.drop_last and len(tail) > 0:
            idx_arr += [tail.tolist()]

        output = list()
        for idx in idx_arr:
            output.append(self.reprocess(data, idx))

        return output


class TextDataset(Dataset):
    def __init__(self, filepath, preprocess_config):
        self.cleaners = preprocess_config["preprocessing"]["text"]["text_cleaners"]
        self.open_set_speaker = preprocess_config['open_set_speaker']
        self.basename, self.speaker, self.text = self.process_meta(
            filepath
        )
        with open(
            os.path.join(
                preprocess_config["path"]["preprocessed_path"], "speakers.json"
            )
        ) as f:
            self.speaker_map = json.load(f)

    def __len__(self):
        return len(self.text)

    def __getitem__(self, idx):
        basename = self.basename[idx]
        if not self.open_set_speaker:
            speaker_id = self.speaker[idx]
            speaker = self.speaker_map[speaker_id]
        else:
            speaker_embed_path = os.path.join(self.preprocessed_path, 'speaker_embedding', basename + '.npy')
            speaker = np.load(speaker_embed_path).astype(np.float32)
        phone = np.array(text_to_sequence(self.text[idx], self.cleaners))

        return (basename, speaker, phone)

    def process_meta(self, filename):
        with open(filename, "r", encoding="utf-8") as f:
            name = []
            speaker = []
            text = []
            for line in f.readlines():
                n, s, t = line.strip("\n").split("|")
                name.append(n)
                speaker.append(s)
                text.append(t)
            return name, speaker, text

    def collate_fn(self, data):
        ids = [d[0] for d in data]
        speakers = np.array([d[1] for d in data])
        texts = [d[2] for d in data]
        text_lens = np.array([text.shape[0] for text in texts])

        texts = pad_1D(texts)

        return ids, speakers, texts, text_lens, max(text_lens)
