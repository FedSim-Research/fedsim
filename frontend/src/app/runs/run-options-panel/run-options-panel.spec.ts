import { TestBed } from '@angular/core/testing';
import { RUN_OPTIONS } from '../run-options';
import { RunOptionsPanel } from './run-options-panel';

describe('aggregation response-delay warning', () => {
  it.each(['hierfl', 'spyker'] as const)('shows the scale warning only when %s delay is enabled', async (architecture) => {
    const fixture = TestBed.createComponent(RunOptionsPanel);
    fixture.componentRef.setInput('options', RUN_OPTIONS[architecture].filter(o => o.requestKey === 'aggregation_delay'));
    fixture.componentRef.setInput('values', { aggregation_delay: false });
    fixture.detectChanges();
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('[role="note"]')).toBeNull();
    fixture.componentRef.setInput('values', { aggregation_delay: true });
    fixture.detectChanges();
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('[role="note"]').textContent).toContain('throughput');
  });
});
