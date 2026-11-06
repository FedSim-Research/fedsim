import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ConfirmationService, MessageService } from 'primeng/api';
import { App } from './app';
import { GraphPersistenceService } from './editor/graph-persistence.service';

describe('App', () => {
  const initializeGraph = vi.fn().mockResolvedValue(undefined);

  beforeEach(async () => {
    initializeGraph.mockClear();
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    });
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
        ConfirmationService,
        { provide: GraphPersistenceService, useValue: { initializeGraph } },
      ],
    }).compileComponents();
  });

  afterEach(() => vi.unstubAllGlobals());

  it('initializes both graph workspaces and opens the editor', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();

    expect(initializeGraph).toHaveBeenCalledTimes(2);
    expect(initializeGraph.mock.calls.map((call) => call[1])).toEqual(['spyker', 'hierfl']);
    expect(fixture.componentInstance.activeMode()).toBe('hierfl');
    expect(fixture.nativeElement.querySelector('vflow')).not.toBeNull();
  });

  it('switches between the editor and the run dashboard', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    fixture.componentInstance.changeView('dashboard');
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('vflow')).toBeNull();
    expect(fixture.nativeElement.querySelector('app-dashboard-view')).not.toBeNull();

    fixture.componentInstance.changeView('editor');
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('vflow')).not.toBeNull();
  });
});
