import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DialogModule } from 'primeng/dialog';

type QuickFact = {
  label: string;
  value: string;
};

type RoleCard = {
  title: string;
  architecture: string[];
  accent: 'hier' | 'spyker' | 'shared';
  summary: string;
  detail: string;
};

type ParameterSpec = {
  label: string;
  key: string;
  appliesTo: string[];
  description: string;
  effect: string;
  format?: string;
  note?: string;
};

@Component({
  selector: 'app-help-dialog',
  standalone: true,
  templateUrl: './help-dialog.component.html',
  styleUrls: ['./help-dialog.component.css'],
  imports: [CommonModule, DialogModule],
})
export class HelpDialog {
  public visible = true;
  public readonly quickFacts: QuickFact[] = [
    {
      label: 'Shared fields',
      value: 'Upload, download, compute factor, and performance sigma are explained once below and then mapped to the node types that use them.',
    },
    {
      label: 'Edge formula',
      value: 'Every edge is described as average plus spread: latency plus jitter, and packet loss plus standard deviation.',
    },
    {
      label: 'Architecture rule',
      value: 'Super Server exists in Hierarchical mode. Spyker has no Super Server but adds extra algorithm settings.',
    },
    {
      label: 'Validation basics',
      value: 'Compute factor must be greater than 0, client count must be at least 1, and packet loss values must stay between 0 and 1.',
    },
  ];

  public readonly roleCards: RoleCard[] = [
    {
      title: 'Super Server',
      architecture: ['Hierarchical'],
      accent: 'hier',
      summary: 'Top-level coordinator above all servers.',
      detail: 'Use it as the global aggregation layer in Hierarchical graphs. Servers connect upward to it, and it does not appear in Spyker graphs.',
    },
    {
      title: 'Server',
      architecture: ['Hierarchical', 'Spyker'],
      accent: 'shared',
      summary: 'Intermediate aggregation and routing layer.',
      detail: 'In Hierarchical mode it sits between clients and the Super Server. In Spyker it is the server that coordinates clients and server-side synchronization.',
    },
    {
      title: 'Client',
      architecture: ['Hierarchical', 'Spyker'],
      accent: 'spyker',
      summary: 'Represents the end devices that train on local data.',
      detail: 'A single client entry can represent many simulated devices through the count field, so you can model a whole client group with one visual item.',
    },
  ];

  public readonly sharedNodeParameters: ParameterSpec[] = [
    {
      label: 'Upload',
      key: 'uploadMbps',
      appliesTo: ['Super Server', 'Server', 'Client'],
      description: 'Outgoing bandwidth of the node in megabits per second.',
      effect: 'Higher upload means model updates, gradients, and messages leave the node faster.',
      format: 'Mbps, minimum 0',
    },
    {
      label: 'Download',
      key: 'downloadMbps',
      appliesTo: ['Super Server', 'Server', 'Client'],
      description: 'Incoming bandwidth of the node in megabits per second.',
      effect: 'Higher download means global weights and incoming updates arrive faster.',
      format: 'Mbps, minimum 0',
    },
    {
      label: 'Compute factor',
      key: 'computeFactor',
      appliesTo: ['Super Server', 'Server', 'Client'],
      description: 'Relative compute strength of a node.',
      effect: 'Higher values represent stronger hardware and reduce the simulated time needed for local work and training.',
      format: 'Number greater than 0',
      note: 'Treat it as relative performance, not an absolute CPU or GPU benchmark.',
    },
    {
      label: 'Performance sigma',
      key: 'performanceSigma',
      appliesTo: ['Super Server', 'Server', 'Client'],
      description: 'The plus/minus spread around compute performance.',
      effect: 'Use it to describe how stable or unstable a device class is. Small sigma means consistent performance; larger sigma means stronger fluctuations.',
      format: 'Number, minimum 0',
      note: 'In the current project the runtime mainly derives effective performance spread from compute factor, so sigma is best read as the intended variability shown in the editor and presets.',
    },
  ];

  public readonly nodeSpecificParameters: ParameterSpec[] = [
    {
      label: 'Name',
      key: 'name',
      appliesTo: ['Super Server', 'Server'],
      description: 'Human-readable label shown on the graph and in presets.',
      effect: 'Improves readability when a graph contains multiple infrastructure nodes.',
      note: 'Clients do not expose a dedicated free-text name field in the sidebar.',
    },
    {
      label: 'Client type',
      key: 'type',
      appliesTo: ['Client'],
      description: 'Preset category for the client group, for example mobile, laptop, or workstation.',
      effect: 'Helps classify the simulated device group and is used for labels and saved presets.',
      note: 'Hierarchical validation requires a client type to be set.',
    },
    {
      label: 'Number of clients',
      key: 'count',
      appliesTo: ['Client'],
      description: 'How many simulated clients are represented by one client entry.',
      effect: 'Lets you scale a scenario without drawing dozens of separate clients.',
      format: 'Integer, minimum 1',
    },
  ];

  public readonly edgeParameters: ParameterSpec[] = [
    {
      label: 'Latency',
      key: 'pingMs',
      appliesTo: [],
      description: 'Base latency or ping of the connection in milliseconds.',
      effect: 'Higher latency slows communication between connected nodes and increases message turnaround time.',
      format: 'Milliseconds, minimum 0',
    },
    {
      label: 'Jitter',
      key: 'jitterMs',
      appliesTo: [],
      description: 'The plus/minus spread around latency.',
      effect: 'Higher jitter makes the link less stable because delivery time varies more strongly from message to message.',
      format: 'Milliseconds, minimum 0',
      note: 'The edge editor shows this as Latency +/- Jitter.',
    },
    {
      label: 'Packet loss',
      key: 'packetloss',
      appliesTo: [],
      description: 'Base fraction of traffic that is dropped on the link.',
      effect: 'Higher packet loss increases retransmissions, delays, and the chance that communication becomes inefficient.',
      format: 'Fraction between 0 and 1',
      note: 'Example: 0.001 means 0.1 percent packet loss.',
    },
    {
      label: 'Packet loss stddev',
      key: 'packetlossStddev',
      appliesTo: [],
      description: 'The plus/minus spread around packet loss.',
      effect: 'Use it when you want a link whose reliability changes over time instead of staying fixed.',
      format: 'Fraction between 0 and 1',
      note: 'The edge editor shows this as Pktloss +/- Stddev.',
    },
  ];

  public readonly commonRunParameters: ParameterSpec[] = [
    {
      label: 'Epochs',
      key: 'epochs',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Number of local training passes each client performs before its update is sent upward.',
      effect: 'More epochs increase local work and can improve local fitting, but they also make each round heavier.',
      format: 'Integer, minimum 1',
    },
    {
      label: 'Learning rate',
      key: 'lr',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Optimizer step size for local client training.',
      effect: 'Higher values make training move faster but can become unstable if set too aggressively.',
      format: 'Positive decimal number',
    },
    {
      label: 'Model complexity',
      key: 'model_complexity',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Scaling factor for simulated computational effort during training.',
      effect: 'Use it to make the same graph behave like a lighter or heavier model without redesigning the topology.',
      format: 'Positive decimal number',
    },
    {
      label: 'Time limit',
      key: 'run_time_limit',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Maximum virtual simulation time.',
      effect: 'The run stops once this limit is reached, even if more work would otherwise continue.',
      format: 'Seconds, greater than 0',
    },
    {
      label: 'Eval interval',
      key: 'eval_interval',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'How often periodic evaluation is triggered during the run.',
      effect: 'Lower intervals give more frequent checkpoints, while higher intervals reduce evaluation overhead.',
      format: 'Seconds, minimum 0',
      note: 'A value of 0 disables periodic evaluation during the run.',
    },
    {
      label: 'GPU budget',
      key: 'gpu_budget',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Total GPU share allocated to the run.',
      effect: 'Lets you model GPU-enabled execution or force a CPU-only run when set to 0.',
      format: 'Decimal number, minimum 0',
      note: 'If both architectures run together, the backend may scale the requested budgets down to fit available GPU capacity.',
    },
    {
      label: 'Seed',
      key: 'seed',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Base random seed used to make stochastic parts of the run reproducible.',
      effect: 'Keeping the seed fixed makes repeated experiments easier to compare.',
      format: 'Integer, minimum 0',
    },
    {
      label: 'Output filename',
      key: 'output_filename',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Name of the output checkpoint file produced by the run.',
      effect: 'Helps keep experiment outputs separate and easier to identify.',
    },
    {
      label: 'Evaluate after run',
      key: 'evaluate_model',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Toggle for a final post-training evaluation once the run completes.',
      effect: 'Returns result metrics such as accuracy and average loss after training finishes.',
    },
  ];

  public readonly hierarchicalParameters: ParameterSpec[] = [
    {
      label: 'Batch size',
      key: 'batch_size',
      appliesTo: ['Hierarchical'],
      description: 'Mini-batch size used for local client training.',
      effect: 'Larger batches reduce the number of optimizer steps per epoch but increase memory demand per step.',
      format: 'Integer, minimum 1',
    },
  ];

  public readonly spykerRuntimeParameters: ParameterSpec[] = [
    {
      label: 'Idle token delay',
      key: 'idle_token_delay',
      appliesTo: ['Spyker'],
      description: 'Delay before a token is forwarded when no immediate synchronization event happens.',
      effect: 'Controls how reactive or conservative Spyker is while waiting for the next synchronization opportunity.',
      format: 'Seconds, minimum 0',
    },
  ];

  public readonly spykerAlgorithmParameters: ParameterSpec[] = [
    {
      label: 'Decay beta',
      key: 'decay_beta',
      appliesTo: ['Spyker'],
      description: 'Decay factor for reducing the influence of frequently updating clients.',
      effect: 'Higher beta penalizes very frequent contributors more strongly.',
      format: 'Decimal number, minimum 0',
    },
    {
      label: 'Min learning rate',
      key: 'min_learning_rate',
      appliesTo: ['Spyker'],
      description: 'Lower bound for the decay-adjusted contribution scaling.',
      effect: 'Prevents a client contribution from shrinking below a minimum useful level.',
      format: 'Positive decimal number',
    },
    {
      label: 'h_inter',
      key: 'h_inter',
      appliesTo: ['Spyker'],
      description: 'Threshold for inter-server drift.',
      effect: 'When drift between servers grows beyond this value, Spyker is more likely to trigger synchronization across servers.',
      format: 'Integer, minimum 1',
    },
    {
      label: 'h_intra',
      key: 'h_intra',
      appliesTo: ['Spyker'],
      description: 'Threshold for intra-server drift.',
      effect: 'Controls when local drift inside a server group is high enough to trigger synchronization.',
      format: 'Integer, minimum 1',
    },
    {
      label: 'Sigmoid phi',
      key: 'sigmoid_phi',
      appliesTo: ['Spyker'],
      description: 'Sharpness parameter of the sigmoid weighting used during server-side aggregation.',
      effect: 'Higher phi makes the weighting react more sharply to age or drift differences.',
      format: 'Positive decimal number',
    },
    {
      label: 'Server learning rate',
      key: 'server_learning_rate',
      appliesTo: ['Spyker'],
      description: 'Aggregation learning rate on the server side.',
      effect: 'Controls how strongly the server model moves toward incoming updates during aggregation.',
      format: 'Positive decimal number',
    },
    {
      label: 'TCP RTO delay',
      key: 'tcp_rto_delay',
      appliesTo: ['Spyker'],
      description: 'Simulated TCP retransmission timeout delay.',
      effect: 'Lets you model additional network recovery delay when communication is unreliable.',
      format: 'Decimal number, minimum 0',
    },
  ];

  public readonly implementationNotes: string[] = [
    'Shared parameters are documented once in this helper so repeated fields do not appear again in multiple sections.',
    'Edges are imported symmetrically by the backend, so one edge defines the link behavior in both directions between the two connected nodes.',
    'Packet loss fields use fractions, not percentages. 0.01 means 1 percent, not 0.01 percent.',
    'GPU budget set to 0 means CPU-only execution.',
    'In Hierarchical mode a client type is required, and in Spyker mode there must be no Super Server.',
  ];

  @Output() close = new EventEmitter<void>();

  public onClose(): void {
    this.visible = false;
    this.close.emit();
  }
}
