import http from 'k6/http';
import { sleep } from 'k6';

export let options = {
  stages: [
    { duration: '1m', target: 50 },    // warmup
    { duration: '2m', target: 200 },   // growth
    { duration: '3m', target: 400 },   // peak
    { duration: '2m', target: 300 },   // stabilize
    { duration: '1m', target: 0 },     // cooldown
  ],
};

export default function () {
  http.get('https://www.workforceskilled.com/');
  http.get('https://www.workforceskilled.com/live-webinars/');
  http.get('https://www.workforceskilled.com/recorded-webinars/');
  sleep(1);
}
