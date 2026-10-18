package com.agentichumans.carddemo;

import com.agentichumans.carddemo.cobol.RunResult;
import java.util.Map;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

/**
 * Run one migrated CardDemo batch program:
 * {@code java -jar carddemo-batch.jar --carddemo.job=posttran|intcalc [--carddemo.*=...]}.
 * Exit code follows the COBOL programs: 0 clean, 4 = some transactions rejected (posttran, normal), 12 = job failed.
 */
@SpringBootApplication
public class CardDemoApplication {

    public static void main(String[] args) {
        System.exit(SpringApplication.exit(SpringApplication.run(CardDemoApplication.class, args)));
    }

    private int rc = 12;

    @Bean
    ApplicationRunner runner(JobLauncher launcher, Map<String, Job> jobs, RunResult result,
                             @Value("${carddemo.job:posttran}") String name) {
        return args -> {
            Job job = jobs.values().iterator().next();
            JobExecution ex = launcher.run(job, new JobParametersBuilder().addLong("run", System.nanoTime()).toJobParameters());
            rc = ex.getStatus() == BatchStatus.COMPLETED ? result.returnCode() : 12;
            System.out.printf("%s: %s rc=%d%n", name, result.summary(), rc);
        };
    }

    @Bean
    ExitCodeGenerator exitCodeGenerator() { return () -> rc; }
}
