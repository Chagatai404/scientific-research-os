import {useEffect, useState} from 'react';
import {preference, savePreference} from './api';

export interface ModelChoice {id: string; label: string; provider: string; reasoning_efforts?: string[]}
export interface ModelCatalog {models: ModelChoice[]; default_model?: string; default_effort?: string; voice: {kokoro: boolean; whisper: boolean; label: string}; notice?: string; ollama?: {available: boolean; models: number; hint: string}}
export const DEFAULT_MODEL = 'codex:gpt-6.1-sol';
export const DEFAULT_EFFORT = 'medium';
const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'];
export function normalizeModel(value: string) {return !value || value === 'codex:default' ? DEFAULT_MODEL : value;}
export function modelLabel(model: string, models: ModelChoice[] = []) {
  return models.find(value => value.id === model)?.label || (normalizeModel(model) === DEFAULT_MODEL ? 'GPT-6.1 Sol' : model.split(':').slice(1).join(':').replace(/[-_]/g, ' ') || 'Choose a model');
}
export function supportedEfforts(model?: ModelChoice) {return model?.reasoning_efforts?.filter(value => EFFORTS.includes(value)) || [];}
export function resolveEffort(effort: string, model?: ModelChoice) {
  const choices = supportedEfforts(model);
  return choices.includes(effort) ? effort : choices.includes(DEFAULT_EFFORT) ? DEFAULT_EFFORT : choices[0];
}
export function effortLabel(effort: string) {return effort === 'xhigh' ? 'Extra high' : effort.charAt(0).toUpperCase() + effort.slice(1);}
export function useModelPreferences(models: ModelChoice[] = []) {
  const read = () => ({model: normalizeModel(preference('model', DEFAULT_MODEL)), effort: preference('effort', DEFAULT_EFFORT)});
  const [value, setValue] = useState(read);
  useEffect(() => {
    const changed = () => setValue(read());
    window.addEventListener('ros:model-preferences', changed); window.addEventListener('storage', changed);
    // Migrate the old provider-default preference to an explicit model.
    savePreference('model', normalizeModel(preference('model', DEFAULT_MODEL)));
    return () => {window.removeEventListener('ros:model-preferences', changed); window.removeEventListener('storage', changed);};
  }, []);
  function update(model: string, effort = value.effort) {
    const next = {model: normalizeModel(model), effort};
    savePreference('model', next.model); savePreference('effort', next.effort); setValue(next);
    window.dispatchEvent(new Event('ros:model-preferences'));
  }
  return {...value, selected: models.find(model => model.id === value.model), selectedEffort: resolveEffort(value.effort, models.find(model => model.id === value.model)), update};
}
