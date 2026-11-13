import { inject } from '@angular/core';
import { HttpContextToken, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { MessageService } from 'primeng/api';
import { catchError, throwError } from 'rxjs';

/** Marks requests whose failures the caller reports itself, e.g. background polling. */
export const SILENT_ERRORS = new HttpContextToken<boolean>(() => false);

export const globalErrorInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.context.get(SILENT_ERRORS)) {
    return next(req);
  }
  const messageService = inject(MessageService);
  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      let detail = 'Unexpected error.';
      if (error.status === 0) {
        detail = 'Backend not reachable.';
      } else if (error.status >= 500) {
        detail = 'Server error. Please try again.';
      } else if (error.error?.detail) {
        detail = String(error.error.detail);
      }
      messageService.add({
        severity: 'error',
        summary: 'Request failed',
        detail,
      });
      return throwError(() => error);
    })
  );
};
