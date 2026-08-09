import { Component } from '@angular/core';
import { SupervisorDashboardComponent } from './pages/supervisor-dashboard/supervisor-dashboard.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [SupervisorDashboardComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  title = 'AiVoiceTagger Supervisor';
}
