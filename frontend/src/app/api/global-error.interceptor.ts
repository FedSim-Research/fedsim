import { inject } from '@angular/core';
import { HttpContextToken, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { ErrorNotifier } from './error-notifier.service';

/** Marks requests whose failures the caller reports itself, e.g. background polling. */
export const SILENT_ERRORS = new HttpContextToken<boolean>(() => false);

export const globalErrorInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.context.get(SILENT_ERRORS)) {
    return next(req);
  }
  const notifier = inject(ErrorNotifier);
  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      let detail = 'Unexpected error.';
      if (error.status === 0) {
        detail = 'Backend not reachable.';
      } else if (error.status >= 500) {
        detail = 'Server error. Please try again.';
      } else if (error.error?.detail) {
        detail = formatDetail(error.error.detail);
      }
      notifier.error('Request failed', detail);
      return throwError(() => error);
    })
  );
};

/** FastAPI sends plain strings for HTTP errors and a list of issues for validation errors. */
function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) {
    return detail
      .map((issue) => (typeof issue?.msg === 'string' ? issue.msg : JSON.stringify(issue)))
      .join('\n');
  }
  return String(detail);
}
