import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Confirmacao } from './shared/confirmacao';

@Component({
  imports: [RouterOutlet, Confirmacao],
  selector: 'app-root',
  templateUrl: './app.html',
})
export class App {}
