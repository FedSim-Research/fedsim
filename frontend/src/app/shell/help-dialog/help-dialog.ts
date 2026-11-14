import { Component, ElementRef, EventEmitter, Output, ViewChild } from '@angular/core';
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

type HelpSection = {
  id: string;
  kicker: string;
  title: string;
};

@Component({
  selector: 'app-help-dialog',
  standalone: true,
  templateUrl: './help-dialog.html',
  styleUrls: ['./help-dialog.css'],
  imports: [CommonModule, DialogModule],
})
export class HelpDialog {
  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;

  public visible = true;
  public showBackToTop = false;
  public readonly tableOfContents: HelpSection[] = [
    { id: 'quick-orientation', kicker: 'Quick orientation', title: 'Topology and parameter units' },
    { id: 'node-roles', kicker: 'Node roles', title: 'What each node is for' },
    { id: 'shared-node-parameters', kicker: 'Shared node parameters', title: 'Performance and bandwidth fields' },
    { id: 'node-specific-parameters', kicker: 'Node-specific parameters', title: 'Fields that are not shared by every node' },
    { id: 'edge-parameters', kicker: 'Edge parameters', title: 'Network behavior between connected nodes' },
    { id: 'run-settings', kicker: 'Run settings', title: 'Parameters used in the start simulation dialog' },
    { id: 'spyker-runtime-parameter', kicker: 'Spyker', title: 'Extra Spyker run parameter' },
    { id: 'spyker-algorithm', kicker: 'Spyker algorithm', title: 'Parameters that shape Spyker synchronization behavior' },
    { id: 'implementation-notes', kicker: 'Run interpretation', title: 'Reading the configured scenario' },
  ];
  public readonly quickFacts: QuickFact[] = [
    {
      label: 'Edge formula',
      value: 'Latency and packet loss use Gaussian mean and standard deviation. Latency is in milliseconds; loss is a fraction.',
    },
    {
      label: 'Architecture rule',
      value: 'Super Server exists in Hierarchical mode. Spyker has no Super Server but adds extra algorithm settings.',
    },
    {
      label: 'Validation basics',
      value: 'Compute factor is positive, client count is a positive integer, and configured packet loss fractions are between 0 and 1.',
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
      accent: 'shared',
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
      label: 'Runtime sigma',
      key: 'performanceSigma',
      appliesTo: ['Super Server', 'Server', 'Client'],
      description: 'Standard deviation of additive Gaussian variation in simulated training time, measured in virtual seconds.',
      effect: 'Zero disables added runtime variation. Larger values increase timing fluctuations around the nominal training duration.',
      format: 'Seconds, minimum 0',
      note: 'Values are in seconds, independently of compute factor. Server aggregation delays are currently not applied by the simulation engines.',
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
      description: 'Standard deviation of Gaussian variation around the configured latency.',
      effect: 'Higher jitter makes the link less stable because delivery time varies more strongly from message to message.',
      format: 'Milliseconds, minimum 0',
      note: 'The edge editor shows mean +/- standard deviation, not fixed minimum and maximum bounds. Negative sampled latency is clamped to zero.',
    },
    {
      label: 'Packet loss',
      key: 'packetloss',
      appliesTo: [],
      description: 'Base fraction of traffic that is dropped on the link.',
      effect: 'Higher values reduce effective throughput and increase simulated transfer time. Individual packets and retransmissions are not simulated.',
      format: 'Fraction between 0 and 1',
      note: 'Example: 0.001 means 0.1 percent packet loss.',
    },
    {
      label: 'Packet loss stddev',
      key: 'packetlossStddev',
      appliesTo: [],
      description: 'Standard deviation of Gaussian variation around the configured packet loss fraction.',
      effect: 'Use it when you want a link whose reliability changes over time instead of staying fixed.',
      format: 'Fraction between 0 and 1',
      note: 'The edge editor shows mean +/- standard deviation. Samples are not clipped to [0, 1]; the effective throughput multiplier has a floor of 0.001.',
    },
  ];

  public readonly commonRunParameters: ParameterSpec[] = [
    {
      label: 'Batch size',
      key: 'batch_size',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Mini-batch size used for local client training.',
      effect: 'Larger batches reduce optimizer steps per epoch and increase memory demand per step.',
      format: 'Integer, minimum 1',
    },
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
      effect: 'Scales the scheduled virtual training duration. The actual CNN architecture remains fixed.',
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
      effect: 'Lower intervals provide more metric points and increase physical evaluation overhead; they do not save intermediate model checkpoints.',
      format: 'Seconds, minimum 0',
      note: 'A value of 0 disables periodic evaluation during the run.',
    },
    {
      label: 'GPU budget',
      key: 'gpu_budget',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Ray GPU resources reserved for server actors.',
      effect: 'Server model evaluation can use CUDA. Client training runs on CPU; zero selects CPU-only execution.',
      format: 'Decimal number, minimum 0',
      note: 'Budgets are Ray resource fractions. Both mode may scale them down to available GPU capacity.',
    },
    {
      label: 'Dataset',
      key: 'dataset',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Hugging Face dataset identifier used to load and partition training data.',
      effect: 'The maintained baseline is CIFAR-10. Other datasets require compatible image/label columns and model preprocessing.',
      format: 'Dataset id string, for example uoft-cs/cifar10',
    },
    {
      label: 'Seed set',
      key: 'seed_set',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Integer seeds controlling model initialization, data assignment and private random streams.',
      effect: 'Match dataset contents, partition assignments and training budgets as well as seeds. Asynchronous callback order can still vary.',
      format: 'Comma-separated integers, each minimum 0',
    },
    {
      label: 'Repetitions',
      key: 'repetitions',
      appliesTo: ['Hierarchical', 'Spyker'],
      description: 'Number of runs generated from the configured seed set.',
      effect: 'This is derived from the number of listed seeds, so a five-seed benchmark produces five repetitions.',
      format: 'Integer, minimum 1',
      note: 'The start dialog derives this automatically from the seed set.',
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
  ];

  public readonly implementationNotes: string[] = [
    'Edges are imported symmetrically by the backend, so one edge defines the link behavior in both directions between the two connected nodes.',
    'Packet loss fields use fractions, not percentages. 0.01 means 1 percent, not 0.01 percent.',
    'Packet loss reduces effective throughput; individual packets and retransmission timeouts are not simulated.',
    'GPU budget set to 0 means CPU-only execution.',
    'In Hierarchical mode a client type is required, and in Spyker mode there must be no Super Server.',
  ];

  @Output() close = new EventEmitter<void>();

  public onScroll(event: Event): void {
    const scrollContainer = event.target as HTMLDivElement | null;
    this.showBackToTop = (scrollContainer?.scrollTop ?? 0) > 320;
  }

  public scrollToSection(sectionId: string): void {
    const scrollContainer = this.scrollContainer?.nativeElement;
    const target = scrollContainer?.querySelector<HTMLElement>(`#${sectionId}`);

    if (!scrollContainer || !target) {
      return;
    }

    const containerRect = scrollContainer.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const top = scrollContainer.scrollTop + targetRect.top - containerRect.top - 12;

    scrollContainer.scrollTo({ top, behavior: 'smooth' });
  }

  public scrollToTop(): void {
    this.scrollContainer?.nativeElement.scrollTo({ top: 0, behavior: 'smooth' });
  }

  public onClose(): void {
    this.scrollContainer?.nativeElement.scrollTo({ top: 0 });
    this.showBackToTop = false;
    this.visible = false;
    this.close.emit();
  }
}
