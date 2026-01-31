import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { Edge } from 'ngx-vflow';
import { EdgeMetrics, EDGE_METRIC_DEFAULTS } from '../../../models/edge-metrics';
import { GraphService } from '../../../services/graph-service';

@Component({
  selector: 'app-edge-metrics-box',
  standalone: true,
  templateUrl: './edge-metrics-box.html',
  styleUrl: './edge-metrics-box.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule],
})
export class EdgeMetricsBoxComponent implements OnChanges {
  @Input({ required: true }) edge!: Edge;
  @Input({ required: true }) graphService!: GraphService<any>;

  public form: EdgeMetrics = { ...EDGE_METRIC_DEFAULTS };

  public ngOnChanges(changes: SimpleChanges): void {
    if (changes['edge']) {
      this.form = { ...EDGE_METRIC_DEFAULTS, ...this.readMetrics() };
    }
  }

  public onBlur(): void {
    this.persistMetrics();
  }

  public stopPropagation(event: Event): void {
    event.stopPropagation();
  }

  public get isSelected(): boolean {
    return Boolean((this.edge as any)?.data?.selected);
  }

  public handleInput(event: Event, field: keyof EdgeMetrics, min = 0, max?: number): void {
    const target = event.target as HTMLInputElement | null;
    if (!target) return;
    const normalized = target.value.replace(',', '.');
    target.value = normalized;
    const numeric = Number(normalized);
    if (!Number.isFinite(numeric)) {
      this.form[field] = EDGE_METRIC_DEFAULTS[field];
      target.value = this.form[field].toString();
      return;
    }
    let clamped = Math.max(min, numeric);
    if (max !== undefined) {
      clamped = Math.min(max, clamped);
    }
    this.form[field] = clamped;
    target.value = this.form[field].toString();
  }

  public formatMetric(field: keyof EdgeMetrics): string {
    return this.form[field]?.toString() ?? '';
  }

  private readMetrics(): EdgeMetrics {
    const data = (this.edge as any)?.data;
    return data?.metrics ?? EDGE_METRIC_DEFAULTS;
  }

  private persistMetrics(): void {
    if (!this.graphService || !this.edge) {
      return;
    }
    this.graphService.updateEdgeMetrics(this.edge.id, this.form);
  }
}
