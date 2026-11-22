import { Architecture } from '../domain/topology';

/**
 * Declarative description of an optional, architecture-specific run control.
 * New controls (or architectures) are added here; the start dialog renders them
 * generically and the request mapping copies them under `requestKey`.
 */
export type RunOptionSection = 'simulation' | 'algorithm';

interface RunOptionBase {
  /** Backend field name (snake_case). */
  requestKey: string;
  label: string;
  help: string;
  /** Visible when an experimental flag is enabled, without opening a tooltip. */
  warning?: string;
  section: RunOptionSection;
  /** Request block the value belongs to. */
  target: 'simulation_settings' | 'spyker_config';
}

export interface ChoiceOption extends RunOptionBase {
  kind: 'choice';
  choices: readonly string[];
  defaultValue: string;
}

export interface NumberOption extends RunOptionBase {
  kind: 'number';
  /** Inclusive lower bound unless `exclusiveMin` is set. */
  min: number;
  exclusiveMin?: boolean;
  /** Exclusive upper bound. */
  maxExclusive?: number;
  integer?: boolean;
  /** `null` means unset: the backend keeps its default. */
  defaultValue: number | null;
}

export interface FlagOption extends RunOptionBase {
  kind: 'flag';
  defaultValue: boolean;
}

export type RunOption = ChoiceOption | NumberOption | FlagOption;
export type RunOptionValue = string | number | boolean | null;
export type RunOptionValues = Record<string, RunOptionValue>;

const DATA_OPTIONS: readonly RunOption[] = [
  {
    kind: 'choice', requestKey: 'event_order', label: 'Event ordering', section: 'simulation',
    target: 'simulation_settings', choices: ['completion', 'parent'], defaultValue: 'completion',
    help: 'completion: children follow physical callback completion. parent: finish each dispatch frontier, then insert children by parent sequence. This experimental tie convention changes scheduling assumptions; fixed seeds alone do not guarantee replay across platforms.',
  },
  {
    kind: 'choice', requestKey: 'partitioning', label: 'Data partitioning', section: 'simulation',
    target: 'simulation_settings', choices: ['iid', 'label-skew'], defaultValue: 'iid',
    help: 'iid: shuffled equal shares; label-skew: each client holds only a few labels (non-IID).',
  },
  {
    kind: 'number', requestKey: 'labels_per_client', label: 'Labels per client', section: 'simulation',
    target: 'simulation_settings', min: 1, integer: true, defaultValue: null,
    help: 'Required for label-skew partitioning (Spyker paper: 2).',
  },
  {
    kind: 'number', requestKey: 'local_holdout', label: 'Local holdout', section: 'simulation',
    target: 'simulation_settings', min: 0, maxExclusive: 1, defaultValue: null,
    help: 'Share of each client partition kept out of training (backend default 0.2; 0 trains on all data).',
  },
];

/** Optional controls per architecture; an architecture without extras maps to []. */
export const RUN_OPTIONS: Readonly<Record<Architecture, readonly RunOption[]>> = {
  hierfl: [
    ...DATA_OPTIONS,
    {
      kind: 'number', requestKey: 'edge_rounds', label: 'Edge rounds', section: 'algorithm',
      target: 'simulation_settings', min: 1, integer: true, defaultValue: null,
      help: 'HierFAVG kappa_2: edge aggregations per coordinator round (backend default 1).',
    },
    {
      kind: 'flag', requestKey: 'aggregation_delay', label: 'Aggregation response delay', section: 'algorithm',
      target: 'simulation_settings', defaultValue: false,
      help: 'Delay coordinator broadcasts only. Model state updates immediately; edge work and server queues are not modeled.',
      warning: 'Supply aggregation throughput in bytes/s. Delay = input model bytes / throughput, plus runtime noise. Model state is immediately visible; server queues are not modeled.',
    },
    {
      kind: 'number', requestKey: 'aggregation_bytes_per_second', label: 'Aggregation throughput (bytes/s)', section: 'algorithm',
      target: 'simulation_settings', min: 0, exclusiveMin: true, defaultValue: null,
      help: 'Required for aggregation response delay. Supply separately measured input-byte throughput; training compute factors are not used. Applied uniformly to coordinator aggregation.',
    },
  ],
  spyker: [
    ...DATA_OPTIONS,
    {
      kind: 'choice', requestKey: 'age_merge', label: 'Peer age merge', section: 'algorithm',
      target: 'spyker_config', choices: ['monotonic', 'weighted'], defaultValue: 'monotonic',
      help: 'monotonic: rounded age that never decreases; weighted: real-valued age as in Alg. 2.',
    },
    {
      kind: 'flag', requestKey: 'sample_weighting', label: 'Sample weighting', section: 'algorithm',
      target: 'spyker_config', defaultValue: false,
      help: 'Scale each client blend by its training-set size relative to the server mean.',
    },
    {
      kind: 'flag', requestKey: 'age_announcements', label: 'Age announcements (RcvAge)', section: 'algorithm',
      target: 'spyker_config', defaultValue: false,
      help: 'Servers without the token announce threshold drift to the token holder.',
    },
    {
      kind: 'flag', requestKey: 'fifo_links', label: 'FIFO server links', section: 'algorithm',
      target: 'spyker_config', defaultValue: false,
      help: 'Deliver server-to-server messages in send order per link.',
    },
    {
      kind: 'flag', requestKey: 'aggregation_delay', label: 'Aggregation response delay', section: 'algorithm',
      target: 'spyker_config', defaultValue: false,
      help: 'Delay the next fit for the replying client. Model state updates immediately; no busy-server queue is modeled.',
      warning: 'Supply aggregation throughput in bytes/s. Delay = input model bytes / throughput, plus runtime noise. Model state is immediately visible; server queues are not modeled.',
    },
    {
      kind: 'number', requestKey: 'aggregation_bytes_per_second', label: 'Aggregation throughput (bytes/s)', section: 'algorithm',
      target: 'spyker_config', min: 0, exclusiveMin: true, defaultValue: null,
      help: 'Required for aggregation response delay. Supply separately measured input-byte throughput; training compute factors are not used. Applied uniformly to server aggregation.',
    },
    {
      kind: 'number', requestKey: 'sync_timeout', label: 'Sync timeout (s)', section: 'algorithm',
      target: 'spyker_config', min: 0, exclusiveMin: true, defaultValue: null,
      help: 'Virtual seconds after which an incomplete exchange round releases the token; empty waits.',
    },
  ],
};

export function defaultOptionValues(architecture: Architecture): RunOptionValues {
  return Object.fromEntries(RUN_OPTIONS[architecture].map((o) => [o.requestKey, o.defaultValue]));
}

/** Returns a readable error for an invalid value, or null. */
export function validateOption(option: RunOption, value: RunOptionValue): string | null {
  if (value === null || value === undefined) return null;
  switch (option.kind) {
    case 'choice':
      return option.choices.includes(value as string) ? null : `${option.label} must be one of ${option.choices.join(', ')}`;
    case 'flag':
      return typeof value === 'boolean' ? null : `${option.label} must be true or false`;
    case 'number': {
      const n = value as number;
      const ok = typeof n === 'number' && Number.isFinite(n)
        && (option.exclusiveMin ? n > option.min : n >= option.min)
        && (option.maxExclusive === undefined || n < option.maxExclusive)
        && (!option.integer || Number.isInteger(n));
      return ok ? null : `${option.label} is out of range`;
    }
  }
}

/** Cross-field rules that a single descriptor cannot express. */
export function validateOptionValues(architecture: Architecture, values: RunOptionValues): string[] {
  const errors = RUN_OPTIONS[architecture]
    .map((option) => validateOption(option, values[option.requestKey] ?? null))
    .filter((error): error is string => error !== null)
    .map((error) => `${architecture}: ${error}`);
  if (values['partitioning'] === 'label-skew' && values['labels_per_client'] == null) {
    errors.push(`${architecture}: label-skew partitioning requires labels per client`);
  }
  if (values['aggregation_delay'] === true && values['aggregation_bytes_per_second'] == null) {
    errors.push(`${architecture}: aggregation response delay requires aggregation throughput (bytes/s)`);
  }
  return errors;
}

export type OptionRequestFields = Record<RunOption['target'], Record<string, RunOptionValue>>;

/** Splits set values into their request blocks; unset values are omitted. */
export function optionRequestFields(
  architecture: Architecture,
  values: RunOptionValues,
): OptionRequestFields {
  const result: OptionRequestFields = { simulation_settings: {}, spyker_config: {} };
  for (const option of RUN_OPTIONS[architecture]) {
    const value = values[option.requestKey];
    if (value !== null && value !== undefined) result[option.target][option.requestKey] = value;
  }
  return result;
}
