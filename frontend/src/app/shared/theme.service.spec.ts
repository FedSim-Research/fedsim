import { DOCUMENT } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  afterEach(() => document.body.classList.remove('light-mode'));

  it('keeps observable selection and document styles in agreement', () => {
    document.body.classList.remove('light-mode');
    const theme = TestBed.inject(ThemeService);
    const body = TestBed.inject(DOCUMENT).body;
    expect(theme.isDark()).toBe(true);
    theme.toggle();
    expect(theme.isDark()).toBe(false);
    expect(body.classList.contains('light-mode')).toBe(true);
    theme.toggle();
    expect(theme.isDark()).toBe(true);
    expect(body.classList.contains('light-mode')).toBe(false);
  });

  it('adopts a light document when initialized', () => {
    document.body.classList.add('light-mode');
    expect(TestBed.inject(ThemeService).isDark()).toBe(false);
  });
});
