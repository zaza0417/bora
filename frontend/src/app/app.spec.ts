import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';

describe('App', () => {
  it('deve criar o app', async () => {
    await TestBed.configureTestingModule({ imports: [App], providers: [provideRouter([])] }).compileComponents();
    expect(TestBed.createComponent(App).componentInstance).toBeTruthy();
  });
});
