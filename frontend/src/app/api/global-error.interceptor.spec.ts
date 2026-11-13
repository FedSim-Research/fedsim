import { HttpClient, HttpContext, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';
import { firstValueFrom } from 'rxjs';
import { globalErrorInterceptor, SILENT_ERRORS } from './global-error.interceptor';

describe('globalErrorInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  const add = vi.fn();

  beforeEach(() => {
    add.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([globalErrorInterceptor])),
        provideHttpClientTesting(),
        { provide: MessageService, useValue: { add } },
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  async function failRequest(context?: HttpContext): Promise<void> {
    const request = firstValueFrom(http.get('/runs', { context })).catch(() => undefined);
    backend.expectOne('/runs').flush(null, { status: 0, statusText: 'Unknown Error' });
    await request;
  }

  it('reports failed requests as a toast', async () => {
    await failRequest();
    expect(add).toHaveBeenCalledWith(expect.objectContaining({ detail: 'Backend not reachable.' }));
  });

  it('lists validation issues instead of [object Object]', async () => {
    const request = firstValueFrom(http.get('/runs')).catch(() => undefined);
    backend.expectOne('/runs').flush(
      { detail: [{ loc: ['body', 'lr'], msg: 'Input should be greater than 0' }] },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await request;
    expect(add).toHaveBeenCalledWith(expect.objectContaining({ detail: 'Input should be greater than 0' }));
  });

  it('stays quiet for requests marked as silent', async () => {
    await failRequest(new HttpContext().set(SILENT_ERRORS, true));
    expect(add).not.toHaveBeenCalled();
  });
});
